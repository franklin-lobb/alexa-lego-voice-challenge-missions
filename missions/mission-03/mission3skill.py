
import logging.handlers
import requests
import uuid

from ask_sdk_core.skill_builder import SkillBuilder
from ask_sdk_core.utils import is_request_type, is_intent_name, get_slot_value
from ask_sdk_core.handler_input import HandlerInput
from ask_sdk_core.serialize import DefaultSerializer

from ask_sdk_model import IntentRequest
from ask_sdk_model.ui import PlayBehavior

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

    return (response_builder
            .speak("Welcome, you can start issuing move commands")
            .ask("Awaiting commands")
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
        .speak("speed set to {} percent.".format(speed))
        .ask("awaiting command")
        .response)

@skill_builder.request_handler(can_handle_func=is_intent_name("MoveIntent"))
def move_intent_handler(handler_input: HandlerInput):
    # Construct and send a custom directive to the connected gadget with
    # data from the MoveIntent request.
    logger.info("MoveIntent received.")

    direction = get_slot_value(handler_input, "Direction")

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
        "direction": direction,
        "duration": duration,
        "speed": speed
    }
    directive = build_send_directive(NAMESPACE, NAME_CONTROL, endpoint_id, payload)

    speak_output = "Applying brake" if (direction == "brake") else (
        "{} {} seconds at {} percent speed".format(direction, duration, speed)
    )

    return (handler_input.response_builder 
            .speak(speak_output)
            .ask("awaiting command")
            .add_directive(directive)
            .response)

@skill_builder.request_handler(can_handle_func=is_intent_name("SetCommandIntent"))
def set_command_intent_handler(handler_input: HandlerInput):
    # Construct and send a custom directive to the connected gadget with data from
    # the SetCommandIntent.
    logger.info("SetCommandIntent received.")

    command = get_slot_value(handler_input, "Command")
    if (command is None):
        return (handler_input.response_builder
                .speak("Can you repeat that?")
                .ask("What was that again?")
                .response)

    session_attr = handler_input.attributes_manager.session_attributes

    endpoint_id = session_attr.get("endpoint_id", [])
    speed = session_attr.get("speed", "50")

    # Construct the directive with the payload containing the move parameters
    payload = {
        "type": "command",
        "command": command,
        "speed": speed
    }
    directive = build_send_directive(NAMESPACE, NAME_CONTROL, endpoint_id, payload)

    speak_output = "command {} activated".format(command)
    return (handler_input.response_builder
            .speak(speak_output)
            .add_directive(directive)
            .response)

@skill_builder.request_handler(can_handle_func=lambda handler_input:
                               is_intent_name("AMAZON.CancelIntent")(handler_input) or
                               is_intent_name("AMAZON.StopIntent")(handler_input))
def stop_and_cancel_intent_handler(handler_input):
    logger.info("Received a Stop or a Cancel Intent..")
    response_builder = handler_input.response_builder

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

lambda_handler = skill_builder.lambda_handler()
