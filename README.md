# alexa-lego-voice-challenge-missions

The 'missions' here are designed to be used as a part of the [Lego MINDSTORMS Voice Challenge: Powered by Alexa](https://www.hackster.io/contests/alexa-lego-voice-challenge)

The Alexa skill code contained here was tested using Python 3.7, which matches the Alexa Hosted Skill environment. Unless otherwise noted, these samples are ported version of the supplied Node.js samples. Interaction models have been included for convenience.

## Using these skills

To use this code, when creating your Alexa skill, choose the **Python Alexa Hosted** option instead of Node.js when selecting the hosting option. Use the the **lambda_function.py** file in the mission folder to update the one hosted with your skill code, and also update the **requirements.txt** file based on the one in the mission folder. The version of the code included here does not use the utils.py file, so it does not need to be updated (nor does it hurt anything to leave it there).

The interaction model (used on the Build tab), is included for your convenience.

## Alternate/Updated Version of Mission 4

Mission folder 4a contains an alternate version of the Mission 4 skill and EV3 program.  The differences include:
* updated interaction model including:
  * two word invocation name
  * expanded sample utterances
  * slot values with synonyms
  * slot values with id's
  * auto-delegation of dialog management, prompting for requires slot values, and validating slot values
* MoveIntent and SetCommandIntent handlers get the id of the slot value and use that in the command passed to the EV3 (This allows new synonyms to be added to the interaction model without needing to update the EV3 code.)
* two new values in the EV3 program's command enums to match the id's specified in the interaction model
