import json
import os
import random
import time
import logging
from typing import Tuple, Optional
from auth import init_auth_state, login_page, show_logout_button

from dotenv import load_dotenv
import anthropic
import streamlit as st

# Configure logging with more detail
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
)

# Constants
CATEGORIES = [
    'Science', 'Technology', 'Engineering', 'Math',
    'Space', 'Animals', 'Nature', 'Geography', "Biology"
]
MAX_PREVIOUS = 10
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds

# Grade level emojis and descriptions
GRADE_INDICATORS = {
    'Elementary': '🎈',
    'Middle': '🌟',
    'High': '🎓'
}

def get_grade_level_info(grade: int) -> Tuple[str, str]:
    """Return the school level and emoji for a given grade."""
    if grade <= 5:
        return 'Elementary', GRADE_INDICATORS['Elementary']
    elif grade <= 8:
        return 'Middle', GRADE_INDICATORS['Middle']
    else:
        return 'High', GRADE_INDICATORS['High']

def load_api_key():
    """Load the Anthropic API key from Streamlit secrets or environment."""
    try:
        # Try to get from streamlit secrets first
        api_key = st.secrets.get("ANTHROPIC_API_KEY", None)
        
        # Fallback to environment variables for local development
        if not api_key:
            load_dotenv()
            api_key = os.getenv("ANTHROPIC_API_KEY")
            
        if not api_key:
            st.error("Anthropic API key is not set. Please configure secrets or .env file.")
            st.stop()
            
        logging.info("API key loaded successfully")
        client = anthropic.Anthropic(api_key=api_key)
        logging.info("Anthropic client created successfully")
        return client
    except Exception as e:
        logging.error(f"Error in load_api_key: {str(e)}")
        st.error(f"Error initializing Anthropic client: {str(e)}")
        st.stop()

def initialize_session_state():
    """Initialize default values in session state."""
    defaults = {
        'score': 0,
        'total_questions': 0,
        'previous_questions': [],
        'used_categories': [],
        'current_question': None,
        'options': [],
        'correct_answer': '',
        'explanation': '',
        'category': '',
        'answered': False,
        'game_over': False,
        'loading_question': False,
        'grade_level': 4,  # Default grade level
        'current_attempts': 0,  # Track attempts for current question
        'total_attempts': 0,    # Track total attempts across all questions
        'retry_mode': False,    # Whether we're in retry mode
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

def prepare_prompt(category: str, previous_questions_str: str) -> str:
    """Prepare the prompt for Claude."""
    grade = st.session_state['grade_level']
    school_level, _ = get_grade_level_info(grade)
    
    prompt = (
        f"You are a creative teacher creating unique and varied trivia questions for {school_level} School students. "
        "Each question should be associated with a specific category. "
        "Avoid repeating any previous questions.\n\n"
        f"Create a new multiple-choice trivia question about {category} suitable for grade {grade}.\n\n"
        "You must respond with a valid JSON object containing exactly these keys: Question, A, B, C, D, Answer, Explanation, and Category.\n\n"
        "The Answer must be either 'A', 'B', 'C', or 'D' corresponding to the correct option.\n\n"
        "Previous questions to avoid:\n"
        f"{previous_questions_str}\n\n"
        "Response format example:\n"
        "{\n"
        '    "Question": "What is 2 + 2?",\n'
        '    "A": "3",\n'
        '    "B": "4",\n'
        '    "C": "5",\n'
        '    "D": "6",\n'
        '    "Answer": "B",\n'
        '    "Explanation": "2 + 2 equals 4.",\n'
        '    "Category": "Math"\n'
        "}\n\n"
        "Ensure your response is exactly in this JSON format with no additional text before or after. "
        "Do not include any markdown formatting or code blocks in your response."
    )
    logging.debug(f"Generated prompt: {prompt}")
    return prompt

def generate_trivia_question(client: anthropic.Anthropic, previous_questions: list, used_categories: list) -> Optional[str]:
    """Generate a new trivia question using Claude API."""
    try:
        available_categories = [cat for cat in CATEGORIES if cat not in used_categories]
        if not available_categories:
            available_categories = CATEGORIES.copy()
            st.session_state['used_categories'] = []

        category = random.choice(available_categories)
        st.session_state['used_categories'].append(category)

        previous = previous_questions[-MAX_PREVIOUS:]
        previous_questions_str = '\n'.join(previous)

        prompt = prepare_prompt(category, previous_questions_str)
        
        logging.info(f"Attempting to generate question for category: {category}")
        
        for attempt in range(MAX_RETRIES):
            try:
                message = client.messages.create(
                    model="claude-3-opus-20240229",
                    max_tokens=300,
                    temperature=1.0,
                    system="You are a creative teacher generating trivia questions. Respond only with valid JSON.",
                    messages=[
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ]
                )
                logging.info("Successfully received response from Claude")
                response_text = message.content[0].text
                logging.debug(f"Claude response: {response_text}")
                return response_text
            except anthropic.APIError as e:
                logging.error(f"Detailed API error: {str(e)}")
                delay = RETRY_DELAY * (2 ** attempt)
                logging.error(f"Claude API error on attempt {attempt + 1}: {e}. Retrying in {delay} seconds.")
                time.sleep(delay)
            except Exception as e:
                logging.error(f"Detailed unexpected error: {str(e)}")
                st.error(f"An unexpected error occurred: {str(e)}")
                return None
        return None
    except Exception as e:
        logging.error(f"Top-level error in generate_trivia_question: {str(e)}")
        st.error(f"Error generating question: {str(e)}")
        return None

def parse_question(question_text: str) -> Tuple[Optional[str], Optional[list], Optional[str], Optional[str], Optional[str]]:
    """Parse the generated question JSON into its components."""
    try:
        # Log the raw response for debugging
        logging.info(f"Raw response from Claude: {question_text}")
        
        # Try to clean the response if it contains markdown code blocks
        if "```json" in question_text:
            question_text = question_text.split("```json")[1].split("```")[0].strip()
        elif "```" in question_text:
            question_text = question_text.split("```")[1].strip()
            
        # Remove any potential leading/trailing whitespace or quotes
        question_text = question_text.strip().strip('"').strip("'")
        
        data = json.loads(question_text)
        required_keys = {'Question', 'A', 'B', 'C', 'D', 'Answer', 'Explanation', 'Category'}
        if not required_keys.issubset(data.keys()):
            missing = required_keys - data.keys()
            error_msg = f"Missing keys in the response: {', '.join(missing)}"
            logging.error(error_msg)
            st.error(error_msg)
            return None, None, None, None, None

        # Validate Answer format
        if data['Answer'] not in ['A', 'B', 'C', 'D']:
            error_msg = f"Invalid Answer format: {data['Answer']}. Must be A, B, C, or D"
            logging.error(error_msg)
            st.error(error_msg)
            return None, None, None, None, None

        question = data['Question'].strip()
        options = [f"{key}) {data[key].strip()}" for key in ['A', 'B', 'C', 'D']]
        answer = data['Answer'].strip().upper()
        explanation = data['Explanation'].strip()
        category = data['Category'].strip()

        # Additional validation
        if not all([question, all(options), answer, explanation, category]):
            error_msg = "One or more fields are empty"
            logging.error(error_msg)
            st.error(error_msg)
            return None, None, None, None, None

        logging.info("Successfully parsed question data")
        return question, options, answer, explanation, category
    except json.JSONDecodeError as e:
        logging.error(f"JSON decoding failed: {e}\nReceived text: {question_text}")
        st.error("Failed to parse the question. The response format was incorrect.")
        return None, None, None, None, None
    except Exception as e:
        logging.error(f"Unexpected error during parsing: {e}")
        st.error("An error occurred while parsing the question.")
        return None, None, None, None, None

def set_new_question():
    """Generate and set a new question in session state."""
    try:
        if st.session_state.get('game_over', False):
            return

        st.session_state['loading_question'] = True
        st.session_state['current_attempts'] = 0  # Reset attempts for new question
        st.session_state['retry_mode'] = False    # Reset retry mode
        
        with st.spinner("Generating a new question..."):
            client = load_api_key()  # Get Claude client
            logging.info("Starting question generation")
            question_text = generate_trivia_question(
                client,
                st.session_state['previous_questions'],
                st.session_state['used_categories']
            )
        
        if question_text:
            question, options, answer, explanation, category = parse_question(question_text)
            if question and options and answer:
                st.session_state.update({
                    'current_question': question,
                    'options': options,
                    'correct_answer': answer,
                    'explanation': explanation,
                    'category': category,
                    'previous_questions': st.session_state['previous_questions'] + [question],
                    'answered': False,
                })
                logging.info("Successfully set new question")
            else:
                st.error("Couldn't parse the question correctly.")
                logging.error("Failed to parse question components")
        else:
            st.error("Failed to generate a question from Claude.")
            logging.error("No question text received from Claude")
            
        st.session_state['loading_question'] = False
    except Exception as e:
        logging.error(f"Error in set_new_question: {str(e)}")
        st.error(f"Error setting new question: {str(e)}")
        st.session_state['loading_question'] = False

def reset_game():
    """Reset the game to its initial state."""
    try:
        st.session_state.update({
            'score': 0,
            'total_questions': 0,
            'previous_questions': [],
            'used_categories': [],
            'current_question': None,
            'options': [],
            'correct_answer': '',
            'explanation': '',
            'category': '',
            'answered': False,
            'game_over': False,
            'loading_question': False,
            'current_attempts': 0,
            'total_attempts': 0,
            'retry_mode': False,
        })
        logging.info("Game reset successfully")
    except Exception as e:
        logging.error(f"Error resetting game: {str(e)}")
        st.error("Failed to reset game")

def submit_answer(selected_option: str):
    """Handle the answer submission."""
    try:
        if not st.session_state['answered']:
            user_answer = selected_option.split(')')[0].strip().upper()
            st.session_state['current_attempts'] += 1
            st.session_state['total_attempts'] += 1

            if user_answer == st.session_state['correct_answer'].upper():
                st.session_state['score'] += 1
                attempt_text = "try" if st.session_state['current_attempts'] == 1 else "tries"
                st.success(f"🎉 Correct! Got it in {st.session_state['current_attempts']} {attempt_text}!")
                logging.info(f"Correct answer submitted after {st.session_state['current_attempts']} attempts")
                st.session_state['answered'] = True
                st.session_state['retry_mode'] = False
                st.info(f"**Explanation:** {st.session_state['explanation']}")
            else:
                st.error("❌ Incorrect! Try again!")
                st.session_state['retry_mode'] = True
                
    except Exception as e:
        logging.error(f"Error in submit_answer: {str(e)}")
        st.error("Error processing answer")

def handle_end_game():
    """Display final score and option to restart the game."""
    try:
        st.write("## Game Over 🎮")
        st.write(f"🎯 You answered **{st.session_state['score']}** out of **{st.session_state['total_questions']}** questions correctly.")
        
        # Calculate and display average attempts
        if st.session_state['total_questions'] > 0:
            avg_attempts = st.session_state['total_attempts'] / st.session_state['total_questions']
            st.write(f"📊 Average attempts per question: **{avg_attempts:.1f}**")
        
        st.write("Thank you for playing the STRAUS Math and Science Trivia Game! 👏")

        if st.button("Restart Game", key="restart_game_button"):
            reset_game()
            st.rerun()
    except Exception as e:
        logging.error(f"Error in handle_end_game: {str(e)}")
        st.error("Error handling game end")

def display_grade_level_indicator():
    """Display visual indicator for current grade level."""
    try:
        grade = st.session_state['grade_level']
        school_level, emoji = get_grade_level_info(grade)
        
        st.sidebar.markdown("---")
        st.sidebar.markdown("### Current Level:")
        col1, col2 = st.sidebar.columns([1, 2])
        with col1:
            st.markdown(f"### {emoji}")
        with col2:
            st.markdown(f"**Grade {grade}**  \n{school_level} School")
    except Exception as e:
        logging.error(f"Error displaying grade level: {str(e)}")
        st.error("Error displaying grade level")

def main():
    """Main application function."""
    try:
        # Initialize authentication state
        init_auth_state()
        
        # Show login page if not authenticated
        if not st.session_state.authenticated:
            login_page()
            return
            
        # Show logout button in sidebar for authenticated users
        show_logout_button()

        # Original app content starts here
        st.title("🧠 The STRAUS Math and Science Trivia Game")
        logging.info("Starting application")
        load_api_key()
        initialize_session_state()

        # Add grade level selector in sidebar with visual feedback
        st.sidebar.header("📚 Settings")
        grade_level = st.sidebar.slider(
            "Select Grade Level",
            min_value=1,
            max_value=12,
            value=st.session_state['grade_level'],
            step=1,
            help="Select the grade level for the questions"
        )
        
        # Update grade level in session state if changed
        if grade_level != st.session_state['grade_level']:
            st.session_state['grade_level'] = grade_level
            st.session_state['current_question'] = None  # Reset current question to get one for new grade level
            logging.info(f"Grade level changed to {grade_level}")
        
        # Display grade level indicator
        display_grade_level_indicator()
            
        # Display the scoreboard in sidebar
        st.sidebar.header("🎯 Your Score")
        st.sidebar.write(f"**Correct Answers:** {st.session_state['score']}")
        st.sidebar.write(f"**Total Questions:** {st.session_state['total_questions']}")
        if st.session_state['total_attempts'] > 0 and st.session_state['total_questions'] > 0:
            avg_attempts = st.session_state['total_attempts'] / st.session_state['total_questions']
            st.sidebar.write(f"**Average Attempts:** {avg_attempts:.1f}")

        # Handle top-level UI controls
        col1, col2 = st.columns(2)
        with col1:
            next_question_clicked = st.button("Next Question", key="next_question_button")
        with col2:
            end_game_clicked = st.button("End Game", key="end_game_button")

        # Handle game over state
        if end_game_clicked:
            st.session_state['game_over'] = True
            logging.info("Game end requested")

        if st.session_state.get('game_over', False):
            handle_end_game()
            return

        # If not game over, handle question generation
        if next_question_clicked:
            logging.info("New question requested")
            set_new_question()

        if st.session_state['current_question'] is None and not st.session_state['loading_question']:
            logging.info("Initial question generation")
            set_new_question()

        if st.session_state['current_question']:
            st.header(f"Category: {st.session_state['category']}")
            st.write(st.session_state['current_question'])

            if not st.session_state['answered'] and not st.session_state['loading_question']:
                if st.session_state['retry_mode']:
                    st.write(f"Attempts so far: {st.session_state['current_attempts']}")
                
                # Using a unique key for radio button based on attempts to force refresh
                selected_option = st.radio(
                    "Choose your answer:", 
                    st.session_state['options'], 
                    key=f"options_radio_{st.session_state['current_attempts']}"
                )
                
                # Using a unique key for submit button based on attempts
                if st.button("Submit Answer", key=f"submit_button_{st.session_state['current_attempts']}"):
                    logging.info("Answer submission attempted")
                    submit_answer(selected_option)

    except Exception as e:
        logging.error(f"Critical error in main function: {str(e)}")
        st.error("An unexpected error occurred in the application")

if __name__ == "__main__":
    main()