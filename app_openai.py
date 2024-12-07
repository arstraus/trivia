import json
import os
import random
import time
import logging
from typing import Tuple, Optional

from dotenv import load_dotenv
import anthropic
import streamlit as st

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

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
    """Load the Anthropic API key from the environment."""
    load_dotenv()
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        st.error("Anthropic API key is not set. Please configure the .env file or use Streamlit secrets.")
        st.stop()
    return anthropic.Client(api_key)

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
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

def prepare_prompt(category: str, previous_questions_str: str) -> str:
    """Prepare the prompt for Claude."""
    grade = st.session_state['grade_level']
    school_level, _ = get_grade_level_info(grade)
    
    return (
        f"You are a creative teacher creating unique and varied trivia questions for {school_level} School students. "
        "Each question should be associated with a specific category. "
        "Avoid repeating any previous questions.\n\n"
        f"Create a new multiple-choice trivia question about {category} suitable for grade {grade}.\n\n"
        "Ensure the question is different from the following list of questions:\n"
        f"{previous_questions_str}\n\n"
        "Format the response as a JSON object with the following keys: Question, A, B, C, D, Answer, Explanation, Category.\n"
        "Example:\n"
        "{\n"
        '    "Question": "What is 2 + 2?",\n'
        '    "A": "3",\n'
        '    "B": "4",\n'
        '    "C": "5",\n'
        '    "D": "6",\n'
        '    "Answer": "B",\n'
        '    "Explanation": "2 + 2 equals 4.",\n'
        '    "Category": "Math"\n'
        "}"
    )

def generate_trivia_question(client: anthropic.Client, previous_questions: list, used_categories: list) -> Optional[str]:
    """Generate a new trivia question using Claude API."""
    available_categories = [cat for cat in CATEGORIES if cat not in used_categories]
    if not available_categories:
        available_categories = CATEGORIES.copy()
        st.session_state['used_categories'] = []

    category = random.choice(available_categories)
    st.session_state['used_categories'].append(category)

    previous = previous_questions[-MAX_PREVIOUS:]
    previous_questions_str = '\n'.join(previous)

    prompt = prepare_prompt(category, previous_questions_str)

    for attempt in range(MAX_RETRIES):
        try:
            response = client.messages.create(
                model="claude-3-opus-20240229",
                max_tokens=300,
                temperature=1.0,
                system="You are a creative teacher generating trivia questions.",
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )
            return response.content[0].text
        except anthropic.APIError as e:
            delay = RETRY_DELAY * (2 ** attempt)
            logging.error(f"Claude API error on attempt {attempt + 1}: {e}. Retrying in {delay} seconds.")
            time.sleep(delay)
        except Exception as e:
            logging.error(f"Unexpected error: {e}")
            st.error("An unexpected error occurred while generating the question.")
            return None
    return None

def parse_question(question_text: str) -> Tuple[Optional[str], Optional[list], Optional[str], Optional[str], Optional[str]]:
    """Parse the generated question JSON into its components."""
    try:
        data = json.loads(question_text)
        required_keys = {'Question', 'A', 'B', 'C', 'D', 'Answer', 'Explanation', 'Category'}
        if not required_keys.issubset(data.keys()):
            missing = required_keys - data.keys()
            st.error(f"Missing keys in the response: {', '.join(missing)}")
            return None, None, None, None, None

        question = data['Question'].strip()
        options = [f"{key}) {data[key].strip()}" for key in ['A', 'B', 'C', 'D']]
        answer = data['Answer'].strip().upper()
        explanation = data['Explanation'].strip()
        category = data['Category'].strip()

        return question, options, answer, explanation, category
    except json.JSONDecodeError as e:
        logging.error(f"JSON decoding failed: {e}")
        st.error("Failed to parse the question. The response format was incorrect.")
        return None, None, None, None, None
    except Exception as e:
        logging.error(f"Unexpected error during parsing: {e}")
        st.error("An error occurred while parsing the question.")
        return None, None, None, None, None

def set_new_question():
    """Generate and set a new question in session state."""
    if st.session_state.get('game_over', False):
        return

    st.session_state['loading_question'] = True
    with st.spinner("Generating a new question..."):
        client = load_api_key()  # Get Claude client
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
        else:
            st.error("Couldn't parse the question correctly.")
    else:
        st.error("Failed to generate a question from Claude.")
    st.session_state['loading_question'] = False

def reset_game():
    """Reset the game to its initial state."""
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
    })

def submit_answer(selected_option: str):
    """Handle the answer submission."""
    if not st.session_state['answered']:
        user_answer = selected_option.split(')')[0].strip().upper()
        st.session_state['total_questions'] += 1

        if user_answer == st.session_state['correct_answer'].upper():
            st.session_state['score'] += 1
            st.success("🎉 Correct! Well done!")
        else:
            correct_option = next(
                (opt for opt in st.session_state['options'] if opt.startswith(st.session_state['correct_answer'] + ')')),
                'Unknown'
            )
            st.error(f"❌ Oops! The correct answer was {correct_option}.")

        st.info(f"**Explanation:** {st.session_state['explanation']}")
        st.session_state['answered'] = True

def handle_end_game():
    """Display final score and option to restart the game."""
    st.write("## Game Over 🎮")
    st.write(f"🎯 You answered **{st.session_state['score']}** out of **{st.session_state['total_questions']}** questions correctly.")
    st.write("Thank you for playing the STRAUS Math and Science Trivia Game! 👏")

    if st.button("Restart Game", key="restart_game_button"):
        reset_game()
        st.rerun()

def display_grade_level_indicator():
    """Display visual indicator for current grade level."""
    grade = st.session_state['grade_level']
    school_level, emoji = get_grade_level_info(grade)
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("### Current Level:")
    col1, col2 = st.sidebar.columns([1, 2])
    with col1:
        st.markdown(f"### {emoji}")
    with col2:
        st.markdown(f"**Grade {grade}**  \n{school_level} School")

def main():
    """Main application function."""
    st.title("🧠 The STRAUS Math and Science Trivia Game")

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
    
    # Display grade level indicator
    display_grade_level_indicator()
        
    # Display the scoreboard in the sidebar
    st.sidebar.header("🎯 Your Score")
    st.sidebar.write(f"**Correct Answers:** {st.session_state['score']}")
    st.sidebar.write(f"**Total Questions:** {st.session_state['total_questions']}")

    # Handle top-level UI controls
    col1, col2 = st.columns(2)
    with col1:
        next_question_clicked = st.button("Next Question", key="next_question_button")
    with col2:
        end_game_clicked = st.button("End Game", key="end_game_button")

    # Handle game over state
    if end_game_clicked:
        st.session_state['game_over'] = True

    if st.session_state.get('game_over', False):
        handle_end_game()
        return

    # If not game over, handle question generation
    if next_question_clicked:
        set_new_question()

    if st.session_state['current_question'] is None and not st.session_state['loading_question']:
        set_new_question()

    if st.session_state['current_question']:
        st.header(f"Category: {st.session_state['category']}")
        st.write(st.session_state['current_question'])

        if not st.session_state['answered'] and not st.session_state['loading_question']:
            selected_option = st.radio("Choose your answer:", st.session_state['options'], key="options_radio")
            if st.button("Submit Answer", key="submit_button"):
                submit_answer(selected_option)

if __name__ == "__main__":
    main()