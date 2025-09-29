# Chatterboxes
###Collaborator: Wenzhuo Ma (wm356)###

## Part 1.
### Text to Speech 
\*\***Write your own shell file to use your favorite of these TTS engines to have your Pi greet you by name.**\*\*

Please find my shell file [here](https://github.com/whyooooo/Interactive-Lab-Hub/blob/Fall2025/Lab%203/greet_by_name.sh).

### Speech to Text

\*\***Write your own shell file that verbally asks for a numerical based input (such as a phone number, zipcode, number of pets, etc) and records the answer the respondent provides.**\*\*

Please find my shell file [here](https://github.com/whyooooo/Interactive-Lab-Hub/blob/Fall2025/Lab%203/ask_number.sh).

Test commands by running:
```bash
./ask_number.sh
```

The script will:
1. Ask "Please tell me your number" using text-to-speech
2. Record 5 seconds of audio input
3. Process the speech using Vosk offline recognition
4. Save the result to `recorded_number.txt`
5. Play back the recognized number using text-to-speech

### 🤖 NEW: AI-Powered Conversations with Ollama

\*\***Try creating a simple voice interaction that combines speech recognition, Ollama processing, and text-to-speech output. Document what you built and how users responded to it.**\*\*

Please find my voice AI assistant script [here](https://github.com/whyooooo/Interactive-Lab-Hub/blob/Fall2025/Lab%203/voice_ai_assistant.py).

Test commands by running:
```bash
python3 voice_ai_assistant.py
```

The script combines:
1. **Real-time speech recognition** using Vosk 
2. **AI processing** using Ollama API  
3. **Text-to-speech output** using Festival

Features:
- Real-time voice input with live transcription feedback
- AI-powered responses using Ollama phi3:mini model
- Voice output using Festival TTS
- Conversation logging to `conversation_log.txt`
- Say "exit" to quit the conversation

**User Response Documentation:**
The voice AI assistant provides a natural conversational experience. All interactions are logged to [conversation_log.txt](conversation_log.txt) with timestamps for easy review and analysis.

### Storyboard

![](storyboard.jpg)

### Verplank Diagram

![](Diagram.jpg)

\*\***Please describe and document your process.**\*\*

Our Recipe Coach is a voice based cooking assistant designed to make the kitchen experience easier and more convenient. It guides users step by step through recipes, offering clear instructions. Beyond these, it provides flexible support such as setting timers, suggesting ingredient substitutions, clarifying cooking terms, and giving reminders when needed. This hands-free interaction is especially helpful for beginner chefs who may feel overwhelmed in the kitchen, allowing them to focus on cooking without worrying about missing a step. The Recipe Coach adapts to the user’s needs, making home cooking both accessible and enjoyable.

### Acting out the dialogue

Here is the link to the video: https://drive.google.com/file/d/1kZfaJgTYqRgGHBQihvGuF6pen10cT4rR/view?usp=sharing

\*\***Describe if the dialogue seemed different than what you imagined when it was acted out, and how.**\*\*

When acted out, the dialogue felt more natural and conversational than simple exchanges between questions and answers. The pauses, confirmations, and follow-up questions made it more engaging and showed how helpful our design is during cooking.

\*\***Feedback**\*\*

"Having a "teacher" I can consult at any time while cooking is a great solution for my pain points. I usually need to watch the tutorial or recipe several times before cooking, but there are still details I forget or need to confirm during the cooking process. However, during these times, I'm often busy controlling the heat, and my hands are always greasy and dirty, making them unsuitable for using a phone. Having a voice assistant that allows me to free my hands is great."
——Dean Xu

"You guys did a good job! The dialogue is just the same as how I expected which I will have with the intelligent machine. The scenario is good enough to use the AI coach chef. I really like it! And the acting is nice as well!"
——Richard Li

### Wizarding with the Pi (optional)
\*\***Describe if the dialogue seemed different than what you imagined, or when acted out, when it was wizarded, and how.**\*\*

Our device simply rely on audio instructions, so using wizarding techniques isn't strictly necessary for our design.

# Lab 3 Part 2

For Part 2, you will redesign the interaction with the speech-enabled device using the data collected, as well as feedback from part 1.

## Prep for Part 2

Updates:

1. Wording / Language

Simplify instructions: Break complex steps into shorter, easy-to-follow phrases.

Instead of: "Whisk the eggs into the mixture slowly while monitoring consistency."

Use: "Slowly add the eggs. Stir until smooth."

2. Interaction: Tap

Purpose: Confirm step completion.

Example: After completing a step, the user taps “Done” or says “Next” to proceed.

## Prototype your system

The system should:
* use the Raspberry Pi 
* use one or more sensors
* require participants to speak to it. 

*Document how the system works*

*Include videos or screencaptures of both the system and the controller.*


## Test the system
Try to get at least two people to interact with your system. (Ideally, you would inform them that there is a wizard _after_ the interaction, but we recognize that can be hard.)

Answer the following:

### What worked well about the system and what didn't?
\*\**your answer here*\*\*

### What worked well about the controller and what didn't?

\*\**your answer here*\*\*

### What lessons can you take away from the WoZ interactions for designing a more autonomous version of the system?

\*\**your answer here*\*\*


### How could you use your system to create a dataset of interaction? What other sensing modalities would make sense to capture?

\*\**your answer here*\*\*




















