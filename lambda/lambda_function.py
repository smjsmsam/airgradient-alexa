# -*- coding: utf-8 -*-
import logging
import os
import boto3
import requests
import json

from ask_sdk_core.skill_builder import CustomSkillBuilder
from ask_sdk_core.utils import is_request_type, is_intent_name
from ask_sdk_core.handler_input import HandlerInput

from ask_sdk_model import Response
from ask_sdk_dynamodb.adapter import DynamoDbAdapter

SKILL_NAME = 'Voice Assistant for AirGradient'
ddb_region = os.environ.get('DYNAMODB_PERSISTENCE_REGION')
ddb_table_name = os.environ.get('DYNAMODB_PERSISTENCE_TABLE_NAME')
ddb_resource = boto3.resource('dynamodb', region_name=ddb_region)
dynamodb_adapter = DynamoDbAdapter(table_name=ddb_table_name, create_table=False, dynamodb_resource=ddb_resource)
sb = CustomSkillBuilder(persistence_adapter=dynamodb_adapter)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

@sb.request_handler(can_handle_func=is_request_type("LaunchRequest"))
def launch_request_handler(handler_input):
    """Handler for Skill Launch.

    Get the persistence attributes, to figure out the game state.
    """
    # type: (HandlerInput) -> Response
    attr = handler_input.attributes_manager.persistent_attributes
    if not attr or attr["token"] == "":
        attr["token"] = ""
        attr["device"] = -1
        speech_text = (
            "Hello, welcome! "
            "To set up the assistant, please enter your token. "
            "This can be found in your AirGradient Dashboard via General Settings > Connectivity > API Access. ")
        reprompt = "Please set up to continue. "
    else:
        speech_text = (
            "Hello, this is your AirGradient Assistant. "
            "What can I do for you today? ")
        reprompt = "Say help if you need help, or quit if you would like to leave. "

    handler_input.attributes_manager.session_attributes = attr

    handler_input.response_builder.speak(speech_text).ask(reprompt)
    return handler_input.response_builder.response


def not_set_up(handler_input):
    """Function that acts as can handle for session state."""
    # type: (HandlerInput) -> bool
    unset = True
    session_attr = handler_input.attributes_manager.session_attributes

    if ("token" in session_attr and session_attr["token"] != ""):
        unset = False
    
    return unset


def not_chosen(handler_input):
    """Function that acts as can handle for session state."""
    # type: (HandlerInput) -> bool
    undecided = True
    session_attr = handler_input.attributes_manager.session_attributes

    if ("device" in session_attr and session_attr["device"] != -1):
        undecided = False
    
    return undecided


def retrieve_devices(handler_input, token):
    """Function to validate token and return device names of a user's account."""
    names = []
    
    query = "https://api.airgradient.com/public/api/v1/locations/measures/current?token={}".format(token)
    response = requests.get(query)
    
    if response.status_code == 200:
        session_attr = handler_input.attributes_manager.session_attributes
        session_attr["token"] = token
        parse_json = json.loads(response.text)
        
        if(len(parse_json) == 1):
            session_attr["device"] = 0
            
        handler_input.attributes_manager.session_attributes = session_attr
        handler_input.attributes_manager.persistent_attributes = session_attr
        handler_input.attributes_manager.save_persistent_attributes()
        
        for device in parse_json:
            names.append(device["locationName"])
    
    return names


@sb.request_handler(can_handle_func=lambda input:
                    not_set_up(input) and
                    is_intent_name("setUp")(input))
def set_up_handler(handler_input):
    """Function that checks and saves AirGradient API token.
    
    This is not a very secure implementation."""
    session_attr = handler_input.attributes_manager.session_attributes
    temp = handler_input.request_envelope.request.intent.slots["token"].value
    
    result = retrieve_devices(handler_input, temp)
    
    if(result):
        if not_chosen(handler_input):
            speech_text = (
                "I see you have {} devices; {}, and {}. "
                "Please choose which device you would like me to check by default, "
                "based on the order listed above (ex. the first one). ".format(len(result), ", ".join(result[:-1]), result[-1]))
            reprompt = "You can change the default device at any time. " #TODO: implement this
        else:
            speech_text = "Saved the token successfully! "
            reprompt = "What can I do for you today? "
    else:
        speech_text = (
            "That token does not work. "
            "Please try again! ")
        reprompt = (
            "You can find your token in AirGradient Dashboard via General Settings > Connectivity > API Access. "
            "If I struggle to hear you properly, try typing it out instead! ")
    
    handler_input.response_builder.speak(speech_text).ask(reprompt)
    return handler_input.response_builder.response


@sb.request_handler(can_handle_func=lambda input:
                    not_set_up(input) and
                    not is_intent_name("AMAZON.CancelIntent")(input) and
                    not is_intent_name("AMAZON.StopIntent")(input) and
                    not is_intent_name("SessionEndedRequest")(input))
def redirect_set_up_handler(handler_input):
    """Function to ensure user adds their token before using commands."""
    speech_text = "Before I can do anything, you will need to let me know your token first. "
    reprompt = "You can find your token in AirGradient Dashboard via General Settings > Connectivity > API Access. "
    
    handler_input.response_builder.speak(speech_text).ask(reprompt)
    return handler_input.response_builder.response


def get_device_info(token, device):
    """Function to validate chosen device and return current information about it."""
    query = "https://api.airgradient.com/public/api/v1/locations/measures/current?token={}".format(token)
    response = requests.get(query)
    
    if response.status_code == 200:
        parse_json = json.loads(response.text)
        
        if len(parse_json) >= device:
            return parse_json[device - 1]
    
    return None #TODO: error handling


@sb.request_handler(can_handle_func=lambda input:
                    not not_set_up(input) and
                    not_chosen(input) and
                    is_intent_name("chooseDevice")(input))
def choose_device_handler(handler_input):
    """Function that sets the default device to check upon."""
    session_attr = handler_input.attributes_manager.session_attributes
    token = session_attr["token"]
    temp = int(handler_input.request_envelope.request.intent.slots["device"].value)
    
    result = get_device_info(token, temp)
    
    if(result):
        session_attr["device"] = temp
        
        handler_input.attributes_manager.session_attributes = session_attr
        handler_input.attributes_manager.persistent_attributes = session_attr
        handler_input.attributes_manager.save_persistent_attributes()
        
        speech_text = "Saved default device successfully! "
        reprompt = "What can I do for you today? "
    else:
        speech_text = (
            "Sorry, that number does not work. "
            "Please choose based on the order listed above (ex. the first one). ")
        reprompt = "You should respond with a number based on the order of devices I have listed. "
    
    handler_input.response_builder.speak(speech_text).ask(reprompt)
    return handler_input.response_builder.response


@sb.request_handler(can_handle_func=lambda input:
                    not not_set_up(input) and
                    not_chosen(input) and
                    not is_intent_name("AMAZON.CancelIntent")(input) and
                    not is_intent_name("AMAZON.StopIntent")(input) and
                    not is_intent_name("SessionEndedRequest")(input))
def redirect_choose_device_handler(handler_input):
    """Function to ensure user chooses device before using commands."""
    session_attr = handler_input.attributes_manager.session_attributes
    token = session_attr["token"]
    
    result = retrieve_devices(handler_input, token)
    
    speech_text = (
        "Based on this list: {}, and {}, "
        "Please choose which device you would like me to check by default, "
        "based on the order listed above (ex. the first one). ".format(", ".join(result[:-1]), result[-1]))
    reprompt = "You should respond with a number based on the order of devices I have listed. "
    
    handler_input.response_builder.speak(speech_text).ask(reprompt)
    return handler_input.response_builder.response


@sb.request_handler(can_handle_func=lambda input:
                    not not_set_up(input) and
                    not not_chosen(input) and
                    is_intent_name("carbonDioxide")(input))
def carbon_dioxide_handler(handler_input):
    """Handler for carbon dioxide."""
    session_attr = handler_input.attributes_manager.session_attributes
    token = session_attr["token"]
    device = session_attr["device"]
    
    result = get_device_info(token, device)
    
    speech_text = "It is currently {} ppm. ".format(result["rco2"])
    reprompt = "What else can I do for you today? "
    
    handler_input.response_builder.speak(speech_text).ask(reprompt)
    return handler_input.response_builder.response


@sb.request_handler(can_handle_func=is_intent_name("AMAZON.HelpIntent"))
def help_intent_handler(handler_input):
    """Handler for Help Intent."""
    # type: (HandlerInput) -> Response
    #TODO: rewrite this
    speech_text = (
        "I am thinking of a number between zero and one hundred, try to "
        "guess it and I will tell you if you got it or it is higher or "
        "lower")
    reprompt = "Try saying a number."

    handler_input.response_builder.speak(speech_text).ask(reprompt)
    return handler_input.response_builder.response


@sb.request_handler(
    can_handle_func=lambda input:
        is_intent_name("AMAZON.CancelIntent")(input) or
        is_intent_name("AMAZON.StopIntent")(input))
def cancel_and_stop_intent_handler(handler_input):
    """Single handler for Cancel and Stop Intent."""
    # type: (HandlerInput) -> Response
    #TODO: rewrite this
    speech_text = "Thanks for playing!!"

    handler_input.response_builder.speak(
        speech_text).set_should_end_session(True)
    return handler_input.response_builder.response


@sb.request_handler(can_handle_func=is_request_type("SessionEndedRequest"))
def session_ended_request_handler(handler_input):
    """Handler for Session End."""
    # type: (HandlerInput) -> Response
    logger.info(
        "Session ended with reason: {}".format(
            handler_input.request_envelope.request.reason))
    return handler_input.response_builder.response


@sb.request_handler(can_handle_func=lambda input:
                    is_intent_name("AMAZON.FallbackIntent")(input))
def fallback_handler(handler_input):
    """AMAZON.FallbackIntent is only available in en-US locale.
    This handler will not be triggered except in that locale,
    so it is safe to deploy on any locale.
    """
    # type: (HandlerInput) -> Response
    #TODO: rewrite this
    session_attr = handler_input.attributes_manager.session_attributes
    
    if ("game_state" in session_attr and
            session_attr["game_state"]=="STARTED"):
        speech_text = (
            "The {} skill can't help you with that.  "
            "Try guessing a number between 0 and 100. ".format(SKILL_NAME))
        reprompt = "Please guess a number between 0 and 100."
    else:
        speech_text = (
            "The {} skill can't help you with that.  "
            "It will come up with a number between 0 and 100 and "
            "you try to guess it by saying a number in that range. "
            "Would you like to play?".format(SKILL_NAME))
        reprompt = "Say yes to start the game or no to quit."

    handler_input.response_builder.speak(speech_text).ask(reprompt)
    return handler_input.response_builder.response


@sb.request_handler(can_handle_func=lambda input: True)
def unhandled_intent_handler(handler_input):
    """Handler for all other unhandled requests."""
    # type: (HandlerInput) -> Response
    #TODO: rewrite this
    speech = "Say yes to continue or no to end the game!!"
    handler_input.response_builder.speak(speech).ask(speech)
    return handler_input.response_builder.response


@sb.exception_handler(can_handle_func=lambda i, e: True)
def all_exception_handler(handler_input, exception):
    """Catch all exception handler, log exception and
    respond with custom message.
    """
    # type: (HandlerInput, Exception) -> Response
    #TODO: rewrite this
    logger.error(exception, exc_info=True)
    speech = "Sorry, I can't understand that. Please say again!!"
    handler_input.response_builder.speak(speech).ask(speech)
    return handler_input.response_builder.response


@sb.global_response_interceptor()
def log_response(handler_input, response):
    """Response logger."""
    # type: (HandlerInput, Response) -> None
    logger.info("Response: {}".format(response))


lambda_handler = sb.lambda_handler()
