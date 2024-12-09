import json
import os
import random
import time
import logging
from typing import Tuple, Optional, Dict, List
from auth import init_auth_state, login_page, show_logout_button

from dotenv import load_dotenv
import anthropic
import streamlit as st

# Configure logging with more detail
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
)

class GameConfig:
    CATEGORIES: List[str] = [
        'Science', 'Technology', 'Engineering', 'Math',
        'Space', 'Animals', 'Nature', 'Geography', 'Biology'
    ]
    MAX_PREVIOUS: int = 10
    MAX_RETRIES: int = 3
    RETRY_DELAY: int = 2
    CLAUDE_MODEL: str = "claude-3-opus-20240229"
    
    GRADE_INDICATORS: Dict[str, str] = {
        'Elementary': '🎈',
        'Middle': '🌟',
        'High': '🎓'
    }

def get_grade_level_info(grade: int) -> Tuple[str, str]:
    """Return the school level and emoji for a given grade."""
    if grade <= 5:
        return 'Elementary', GameConfig.GRADE_INDICATORS['Elementary']
    elif grade <= 8:
        return 'Middle', GameConfig.GRADE_INDICATORS['Middle']
    return 'High', GameConfig.GRADE_INDICATORS['High']

class AnthropicClient:
    @staticmethod
    def create() -> anthropic.Anthropic:
        """Create and return an Anthropic client instance."""
        try:
            # Try to get from streamlit secrets first
            api_key = st.secrets.get("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                st.error("Anthropic API key is not set. Please configure secrets or .env file.")
                st.stop()
                
            logging.info("API key loaded successfully")
            return anthropic.Anthropic(api_key=api_key)
        except Exception as e:
            logging.error(f"Error in create_client: {str(e)}")
            st.error(f"Error initializing Anthropic client: {str(e)}")
            st.stop()

class SessionState:
    """Class to manage session state initialization and updates."""
    @staticmethod
    def initialize() -> None:
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
            'grade_level': 4,
            'current_attempts': 0,
            'total_attempts': 0,
            'retry_mode': False,
        }
        for key, value in defaults.items():
            if key not in st.session_state:
                st.session_state[key] = value

    @staticmethod
    def reset_game() -> None:
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

class QuestionGenerator:
    def __init__(self, client: anthropic.Anthropic):
        self.client = client

    def prepare_prompt(self, category: str, previous_questions: List[str]) -> str:
        """Prepare the prompt for Claude."""
        grade = st.session_state['grade_level']
        school_level, _ = get_grade_level_info(grade)
        
        return (
            f"You are a creative teacher creating unique and varied trivia questions for {school_level} School students. "
            "Each question should be associated with a specific category. "
            "Avoid repeating any previous questions.\n\n"
            f"Create a new multiple-choice trivia question about {category} suitable for grade {grade}.\n\n"
            "You must respond with a valid JSON object containing exactly these keys: "
            "Question, A, B, C, D, Answer, Explanation, and Category.\n\n"
            "The Answer must be either 'A', 'B', 'C', or 'D' corresponding to the correct option.\n\n"
            f"Previous questions to avoid:\n{chr(10).join(previous_questions)}\n\n"
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

    def generate_question(self, previous_questions: List[str], used_categories: List[str]) -> Optional[str]:
        """Generate a new trivia question using Claude API."""
        try:
            available_categories = [cat for cat in GameConfig.CATEGORIES if cat not in used_categories]
            if not available_categories:
                available_categories = GameConfig.CATEGORIES.copy()
                st.session_state['used_categories'] = []

            category = random.choice(available_categories)
            st.session_state['used_categories'].append(category)

            previous = previous_questions[-GameConfig.MAX_PREVIOUS:]
            prompt = self.prepare_prompt(category, previous)
            
            logging.info(f"Attempting to generate question for category: {category}")
            
            for attempt in range(GameConfig.MAX_RETRIES):
                try:
                    message = self.client.messages.create(
                        model=GameConfig.CLAUDE_MODEL,
                        max_tokens=300,
                        temperature=1.0,
                        system="You are a creative teacher generating trivia questions. Respond only with valid JSON.",
                        messages=[{"role": "user", "content": prompt}]
                    )
                    logging.info("Successfully received response from Claude")
                    return message.content[0].text
                except anthropic.APIError as e:
                    delay = GameConfig.RETRY_DELAY * (2 ** attempt)
                    logging.error(f"Claude API error on attempt {attempt + 1}: {e}. Retrying in {delay} seconds.")
                    time.sleep(delay)
            return None
        except Exception as e:
            logging.error(f"Error in generate_question: {str(e)}")
            st.error(f"Error generating question: {str(e)}")
            return None

    def parse_question(self, question_text: str) -> Tuple[Optional[str], Optional[list], Optional[str], Optional[str], Optional[str]]:
        """Parse the generated question JSON into its components."""
        try:
            logging.info(f"Raw response from Claude: {question_text}")
            
            if "```json" in question_text:
                question_text = question_text.split("```json")[1].split("```")[0].strip()
            elif "```" in question_text:
                question_text = question_text.split("```")[1].strip()
                
            question_text = question_text.strip().strip('"').strip("'")
            
            data = json.loads(question_text)
            required_keys = {'Question', 'A', 'B', 'C', 'D', 'Answer', 'Explanation', 'Category'}
            if not required_keys.issubset(data.keys()):
                missing = required_keys - data.keys()
                error_msg = f"Missing keys in the response: {', '.join(missing)}"
                logging.error(error_msg)
                st.error(error_msg)
                return None, None, None, None, None

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

class GameUI:
    @staticmethod
    def display_grade_level_indicator() -> None:
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

    @staticmethod
    def display_scoreboard() -> None:
        """Display the scoreboard in the sidebar."""
        st.sidebar.header("🎯 Your Score")
        st.sidebar.write(f"**Correct Answers:** {st.session_state['score']}")
        st.sidebar.write(f"**Total Questions:** {st.session_state['total_questions']}")
        if st.session_state['total_attempts'] > 0 and st.session_state['total_questions'] > 0:
            avg_attempts = st.session_state['total_attempts'] / st.session_state['total_questions']
            st.sidebar.write(f"**Average Attempts:** {avg_attempts:.1f}")

    @staticmethod
    def handle_end_game() -> None:
        """Display final score and option to restart the game."""
        try:
            st.write("## Game Over 🎮")
            st.write(f"🎯 You answered **{st.session_state['score']}** out of "
                    f"**{st.session_state['total_questions']}** questions correctly.")
            
            if st.session_state['total_questions'] > 0:
                avg_attempts = st.session_state['total_attempts'] / st.session_state['total_questions']
                st.write(f"📊 Average attempts per question: **{avg_attempts:.1f}**")
            
            st.write("Thank you for playing the STRAUS Math and Science Trivia Game! 👏")

            if st.button("Restart Game", key="restart_game_button"):
                SessionState.reset_game()
                st.rerun()
        except Exception as e:
            logging.error(f"Error in handle_end_game: {str(e)}")
            st.error("Error handling game end")

class GameLogic:
    def __init__(self, question_generator: QuestionGenerator):
        self.question_generator = question_generator

    def set_new_question(self) -> None:
        """Generate and set a new question in session state."""
        try:
            if st.session_state.get('game_over', False):
                return

            st.session_state['loading_question'] = True
            st.session_state['current_attempts'] = 0
            st.session_state['retry_mode'] = False
            
            with st.spinner("Generating a new question..."):
                logging.info("Starting question generation")
                question_text = self.question_generator.generate_question(
                    st.session_state['previous_questions'],
                    st.session_state['used_categories']
                )
            
            if question_text:
                question, options, answer, explanation, category = self.question_generator.parse_question(question_text)
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

    def submit_answer(self, selected_option: str) -> None:
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

def main():
    """Main application function."""
    try:
        # Initialize authentication state
        init_auth_state()
        
        if not st.session_state.authenticated:
            login_page()
            return
            
        show_logout_button()
        
        st.title("🧠 The STRAUS Math and Science Trivia Game")
        logging.info("Starting application")
        
        client = AnthropicClient.create()
        SessionState.initialize()
        question_generator = QuestionGenerator(client)
        game_logic = GameLogic(question_generator)
        
        # Grade level selector in sidebar
        st.sidebar.header("📚 Settings")
        grade_level = st.sidebar.slider(
            "Select Grade Level",
            min_value=1,
            max_value=12,
            value=st.session_state['grade_level'],
            step=1,
            help="Select the grade level for the questions"
        )
        
        # Update grade level if changed
        if grade_level != st.session_state['grade_level']:
            st.session_state['grade_level'] = grade_level
            st.session_state['current_question'] = None
            logging.info(f"Grade level changed to {grade_level}")
        
        # Display UI elements
        GameUI.display_grade_level_indicator()
        GameUI.display_scoreboard()

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
            GameUI.handle_end_game()
            return

        # Handle question generation and game flow
        if next_question_clicked:
            logging.info("New question requested")
            game_logic.set_new_question()

        if st.session_state['current_question'] is None and not st.session_state['loading_question']:
            logging.info("Initial question generation")
            game_logic.set_new_question()

        # Display current question and handle answers
        if st.session_state['current_question']:
            st.header(f"Category: {st.session_state['category']}")
            st.write(st.session_state['current_question'])

            if not st.session_state['answered'] and not st.session_state['loading_question']:
                if st.session_state['retry_mode']:
                    st.write(f"Attempts so far: {st.session_state['current_attempts']}")
                
                selected_option = st.radio(
                    "Choose your answer:", 
                    st.session_state['options'], 
                    key=f"options_radio_{st.session_state['current_attempts']}"
                )
                
                if st.button("Submit Answer", key=f"submit_button_{st.session_state['current_attempts']}"):
                    logging.info("Answer submission attempted")
                    game_logic.submit_answer(selected_option)

    except Exception as e:
        logging.error(f"Critical error in main function: {str(e)}")
        st.error("An unexpected error occurred in the application")

if __name__ == "__main__":
    main()