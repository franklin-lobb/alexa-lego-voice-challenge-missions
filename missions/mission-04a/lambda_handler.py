# Mission 04 (alternate version) of the Lego MINDSTORMS Voice Challenge: Powered by Alexa
# Ported to Python by Franklin Lobb
# Original version supplied by Amazon

import logging.handlers
import requests
import uuid

from ask_sdk_core.skill_builder import SkillBuilder
from ask_sdk_core.utils import is_request_type, is_intent_name, get_slot_value, get_slot
from ask_sdk_core.handler_input import HandlerInput
from ask_sdk_core.serialize import DefaultSerializer

from ask_sdk_model import IntentRequest
from ask_sdk_model.ui import PlayBehavior
from ask_sdk_model.slot import Slot

from ask_sdk_model.interfaces.custom_interface_controller import (
    StartEventHandlerDirective, EventFilter, Expiration, FilterMatchAction,
    StopEventHandlerDirective,
    SendDirectiveDirective,
    Header,
    Endpoint,
    EventsReceivedRequest,
    ExpiredRequest
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)
serializer = DefaultSerializer()
skill_builder = SkillBuilder()

# The namespace of the custom directive to be sent by this skill
NAMESPACE = "Custom.Mindstorms.Gadget"

# The name of the custom directive to be sent this skill
NAME_CONTROL = "control"

# The audio tag to include background music
BG_MUSIC = '<audio src="soundbank://soundlibrary/ui/gameshow/amzn_ui_sfx_gameshow_waiting_loop_30s_01"/>'

@skill_builder.request_handler(can_handle_func=is_request_type("LaunchRequest"))
def launch_request_handler(handler_input: HandlerInput):
    logger.info("== Launch Intent ==")

    response_builder = handler_input.response_builder

    system = handler_input.request_envelope.context.system
    api_access_token = system.api_access_token
    api_endpoint = system.api_endpoint

    # Get connected gadget endpoint ID.
    endpoints = get_connected_endpoints(api_endpoint, api_access_token)
    logger.debug("Checking endpoint..")
    if not endpoints:
        logger.debug("No connected gadget endpoints available.")
        return (response_builder
                .speak("I couldn't find an EV3 Brick connected to this Echo device. Please check to make sure your EV3 Brick is connected, and try again.")
                .set_should_end_session(True)
                .response)

    endpoint_id = endpoints[0].get("endpointId", "")

    # Store endpoint ID for using it to send custom directives later.
    logger.debug("Received endpoints. Storing Endpoint Id: %s", endpoint_id)
    session_attr = handler_input.attributes_manager.session_attributes
    session_attr["endpoint_id"] = endpoint_id

    # Set skill duration to 5 minutes (ten 30-seconds interval)
    session_attr["duration"] = 10

    # Set the token to track the event handler
    token = handler_input.request_envelope.request.request_id
    session_attr["token"] = token

    speak_output = "Welcome, voice interface activated"

    return (response_builder
            .speak(speak_output + BG_MUSIC)
            .add_directive(build_start_event_handler_directive(token, 60000, NAMESPACE, NAME_CONTROL, 'SEND', {}))
            .response)

@skill_builder.request_handler(can_handle_func=is_intent_name("SetSpeedIntent"))
def set_speed_intent_handler(handler_input: HandlerInput):
    # Add the speed value to the session attribute.
    # This allows other intent handler to use the specified speed value
    # without asking the user for input.

    logger.info("SetSpeedIntent received.")

    session_attr = handler_input.attributes_manager.session_attributes

    # Bound speed to (1-100)
    speed = get_slot_value("Speed")(handler_input)
    speed = max(1, min(100, int(speed)))
    session_attr["speed"] = speed

    response_builder = handler_input.response_builder

    return (response_builder
        .speak("speed set to {} percent.".format(speed) + BG_MUSIC)
        .response)

def get_id_from_slot(slot: Slot):
    """ returns the slot's id if there was a match, else the spoken value
    """
    if slot is None:
        return ""
    try:
        # grab the first id from the first match (assumes only static entities)
        return slot.resolutions.resolutions_per_authority[0].values[0].value.id
    except Exception as e:
        logger.error('Failed to get id: '+ str(e))
        # if it doesn't work, then there is no id available, so just return the slot's value
        try:
            return slot.value
        except:
            # if for some reason the slot is present, but there is no value
            return ""

@skill_builder.request_handler(can_handle_func=is_intent_name("MoveIntent"))
def move_intent_handler(handler_input: HandlerInput):
    # Construct and send a custom directive to the connected gadget with
    # data from the MoveIntent request.
    logger.info("MoveIntent received.")

    direction = get_slot(handler_input, "Direction" )
    direction_id = get_id_from_slot(direction)
    spoken_direction = get_slot_value(handler_input, "Direction")

    # Duration is optional, use default if not available
    duration = get_slot_value(handler_input, "Duration")
    if duration is None:
        duration = 2

    # Get data from session attribute
    session_attr = handler_input.attributes_manager.session_attributes

    speed = session_attr.get("speed", "50")
    endpoint_id = session_attr.get("endpoint_id", [])

    # Construct the directive with the payload containing the move parameters
    payload = {
        "type": "move",
        "direction": direction_id,
        "duration": duration,
        "speed": speed
    }
    directive = build_send_directive(NAMESPACE, NAME_CONTROL, endpoint_id, payload)

    speak_output = "Applying brake" if (direction_id == "stop") else (
        "{} {} seconds at {} percent speed".format(spoken_direction, duration, speed)
    )

    return (handler_input.response_builder 
            .speak(speak_output)
            .add_directive(directive)
            .response)

@skill_builder.request_handler(can_handle_func=is_intent_name("SetCommandIntent"))
def set_command_intent_handler(handler_input: HandlerInput):
    # Construct and send a custom directive to the connected gadget with data from
    # the SetCommandIntent.
    logger.info("SetCommandIntent received.")

    command = get_slot(handler_input, "Command")

    if (command is None):
        # no slot in request
        return (handler_input.response_builder
                .speak("Can you repeat that?")
                .ask("What was that again?")
                .response)

    command_id = get_id_from_slot(command)
    spoken_command = get_slot_value(handler_input, "Command")

    session_attr = handler_input.attributes_manager.session_attributes

    endpoint_id = session_attr.get("endpoint_id", [])
    speed = session_attr.get("speed", "50")

    # Construct the directive with the payload containing the move parameters
    payload = {
        "type": "command",
        "command": command_id,
        "speed": speed
    }
    directive = build_send_directive(NAMESPACE, NAME_CONTROL, endpoint_id, payload)

    speak_output = "command {} activated".format(spoken_command)
    return (handler_input.response_builder
            .speak(speak_output + BG_MUSIC)
            .add_directive(directive)
            .response)

def has_valid_token(handler_input):
    if not is_request_type('CustomInterfaceController.EventsReceived')(handler_input):
        return False

    session_attr = handler_input.attributes_manager.session_attributes
    request = handler_input.request_envelope.request

    # Validate event token
    if session_attr.get("token", None) != request.token:
        logger.info("Event token doesn't match. Ignoring this event")
        return False

    return True

def has_valid_endpoint(handler_input):
    if not is_request_type('CustomInterfaceController.EventsReceived')(handler_input):
        return False

    session_attr = handler_input.attributes_manager.session_attributes
    request = handler_input.request_envelope.request
    custom_event = request.events[0]

    # Validate endpoint
    request_endpoint = custom_event.endpoint.endpoint_id
    if request_endpoint != session_attr.get("endpoint_id", None):
        logger.info("Event endpoint id doesn't match. Ignoring this event")
        return False

    return True

@skill_builder.request_handler(can_handle_func=lambda handler_input:
    is_request_type("CustomInterfaceController.EventsReceived") and
    has_valid_token(handler_input) and 
    has_valid_endpoint(handler_input)
)
def events_received_request_handler(handler_input: HandlerInput):
    logger.info("== Received Custom Event ==")

    custom_event = handler_input.request_envelope.request.events[0]
    payload = custom_event.payload
    name = custom_event.header.name

    speak_output = ""
    if name == 'Proximity':
        distance = int(payload.get("distance"))
        if distance < 10:
            speak_output = "Intruder detected! What would you like to do?"
            return (handler_input.response_builder
                .speak(speak_output, "REPLACE_ALL")
                .set_should_end_session(False)
                .response)
    elif name == 'Sentry':
        if 'fire' in payload:
            speak_output = "Threat eliminated"
    elif name == 'Speech':
        speak_output = payload.get("speechOut", "")
    else:
        speak_output = "Event not recognized. Awaiting new command."

    return (handler_input.response_builder
        .speak(speak_output + BG_MUSIC, "REPLACE_ALL")
        .response)

@skill_builder.request_handler(can_handle_func=is_request_type("CustomInterfaceController.Expired"))
def custom_interface_expiration_handler(handler_input):
    logger.info("== Custom Event Expiration Input ==")

    session_attr = handler_input.attributes_manager.session_attributes
    
    # Set the token to track the event handler
    token = handler_input.request_envelope.request.request_id
    session_attr["token"] = token

    duration = session_attr.get("duration", 0)
    if duration > 0:
        session_attr["duration"] = duration - 1 
        # extends skill session
        speak_output = "{} minutes remaining.".format(duration)
        timeout = 60000
        directive = build_start_event_handler_directive(token, timeout, NAMESPACE, NAME_CONTROL, 'SEND', {})
        return (handler_input.response_builder
            .add_directive(directive)
            .speak(speak_output + BG_MUSIC)
            .response
        )
    else:
        # End skill session
        return (handler_input.response_builder
            .speak("Skill duration expired. Goodbye.")
            .set_should_end_session(True)
            .response)

@skill_builder.request_handler(can_handle_func=lambda handler_input:
                               is_intent_name("AMAZON.CancelIntent")(handler_input) or
                               is_intent_name("AMAZON.StopIntent")(handler_input))
def stop_and_cancel_intent_handler(handler_input):
    logger.info("Received a Stop or a Cancel Intent..")
    session_attr = handler_input.attributes_manager.session_attributes
    response_builder = handler_input.response_builder

    # When the user stops the skill, stop the EventHandler
    if 'token' in session_attr.keys():
        logger.debug("Active session detected, sending stop EventHandlerDirective.")
        directive = build_stop_event_handler_directive(session_attr["token"])
        response_builder.add_directive(directive)

    return (response_builder
            .speak("Goodbye!")
            .set_should_end_session(True)
            .response)

@skill_builder.request_handler(can_handle_func=is_request_type("SessionEndedRequest"))
def session_ended_request_handler(handler_input):
    logger.info("Session ended with reason: " +
                handler_input.request_envelope.request.reason.to_str())
    return handler_input.response_builder.response

@skill_builder.exception_handler(can_handle_func=lambda i, e: True)
def error_handler(handler_input, exception):
    logger.info("==Error==")
    logger.error(exception, exc_info=True)
    return (handler_input.response_builder
            .speak("I'm sorry, something went wrong!").response)

@skill_builder.global_request_interceptor()
def log_request(handler_input):
    # Log the request for debugging purposes.
    logger.info("==Request==\r" +
                str(serializer.serialize(handler_input.request_envelope)))

@skill_builder.global_response_interceptor()
def log_response(handler_input, response):
    # Log the response for debugging purposes.
    logger.info("==Response==\r" + str(serializer.serialize(response)))
    logger.info("==Session Attributes==\r" +
                str(serializer.serialize(handler_input.attributes_manager.session_attributes)))

def get_connected_endpoints(api_endpoint, api_access_token):
    headers = {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer {}'.format(api_access_token)
    }

    api_url = api_endpoint + "/v1/endpoints"
    endpoints_response = requests.get(api_url, headers=headers)

    if endpoints_response.status_code == requests.codes.get("ok", ""):
        return endpoints_response.json()["endpoints"]

def build_send_directive(namespace, name, endpoint_id, payload):
    return SendDirectiveDirective(
        header=Header(
            name=name,
            namespace=namespace
        ),
        endpoint=Endpoint(
            endpoint_id=endpoint_id
        ),
        payload=payload
    )

def build_start_event_handler_directive(token, duration_ms, namespace,
                                        name, filter_match_action, expiration_payload):
    return StartEventHandlerDirective(
        token=token,
        # event_filter=EventFilter(
        #     filter_expression={
        #         'and': [
        #             {'==': [{'var': 'header.namespace'}, namespace]},
        #             {'==': [{'var': 'header.name'}, name]}
        #         ]
        #     },
        #     filter_match_action=filter_match_action
        # ),
        expiration=Expiration(
            duration_in_milliseconds=duration_ms,
            expiration_payload=expiration_payload))

def build_stop_event_handler_directive(token):
    return StopEventHandlerDirective(token=token)

lambda_handler = skill_builder.lambda_handler()
