import json
import os
import random
import time
import logging
from typing import Tuple, Optional, Dict, List
from auth import init_auth_state, login_page, show_logout_button
import streamlit as st
from datetime import datetime
from dotenv import load_dotenv
import anthropic

# Configure logging with more detail
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
)

class GameTheme:
    """Theme configuration for the game"""
    COLORS = {
        'primary': '#1E88E5',       # Blue
        'success': '#4CAF50',       # Green
        'warning': '#FFC107',       # Amber
        'error': '#FF5252',         # Red
        'info': '#2196F3',         # Light Blue
        'background': '#F8F9FA'     # Light Gray
    }
    
    CUSTOM_CSS = """
        <style>
            .stApp {
                background-color: #F8F9FA;
            }
            
            .main-header {
                font-size: 2.5rem;
                color: #1E88E5;
                text-align: center;
                margin-bottom: 2rem;
            }
            
            .category-badge {
                background-color: #E3F2FD;
                padding: 0.5rem 1rem;
                border-radius: 1rem;
                color: #1E88E5;
                font-weight: bold;
            }
            
            .question-card {
                background-color: white;
                padding: 2rem;
                border-radius: 1rem;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                margin: 1rem 0;
            }
            
            .stats-card {
                background-color: white;
                padding: 1rem;
                border-radius: 0.5rem;
                box-shadow: 0 1px 3px rgba(0,0,0,0.1);
                margin-bottom: 1rem;
            }
            
            .option-button {
                transition: all 0.3s;
            }
            
            .option-button:hover {
                background-color: #E3F2FD;
                cursor: pointer;
            }
        </style>
    """

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
    def setup_page():
        """Configure the basic page layout and styling"""
        st.set_page_config(
            page_title="STRAUS Math & Science Trivia",
            page_icon="🧠",
            layout="wide",
            initial_sidebar_state="expanded"
        )
        st.markdown(GameTheme.CUSTOM_CSS, unsafe_allow_html=True)

    @staticmethod
    def display_header():
        """Display the main game header"""
        st.markdown(
            '<h1 class="main-header">🧠 STRAUS Math & Science Trivia</h1>',
            unsafe_allow_html=True
        )
        st.markdown(
            "<p style='text-align: center; color: #666;'>Test your knowledge across various STEM subjects!</p>",
            unsafe_allow_html=True
        )

    @staticmethod
    def display_stats_dashboard():
        """Display game statistics in a dashboard layout"""
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown(
                f"""
                <div class="stats-card">
                    <h3 style="margin:0; color: #1E88E5;">Score</h3>
                    <h2 style="margin:0;">{st.session_state['score']}</h2>
                </div>
                """,
                unsafe_allow_html=True
            )
        
        with col2:
            if st.session_state['total_questions'] > 0:
                accuracy = (st.session_state['score'] / st.session_state['total_questions']) * 100
            else:
                accuracy = 0
            st.markdown(
                f"""
                <div class="stats-card">
                    <h3 style="margin:0; color: #1E88E5;">Accuracy</h3>
                    <h2 style="margin:0;">{accuracy:.1f}%</h2>
                </div>
                """,
                unsafe_allow_html=True
            )
            
        with col3:
            if st.session_state['total_attempts'] > 0 and st.session_state['total_questions'] > 0:
                avg_attempts = st.session_state['total_attempts'] / st.session_state['total_questions']
            else:
                avg_attempts = 0
            st.markdown(
                f"""
                <div class="stats-card">
                    <h3 style="margin:0; color: #1E88E5;">Avg Attempts</h3>
                    <h2 style="margin:0;">{avg_attempts:.1f}</h2>
                </div>
                """,
                unsafe_allow_html=True
            )

    @staticmethod
    def display_question(question: str, category: str):
        """Display the current question in a card layout"""
        st.markdown(
            f"""
            <div class="question-card">
                <span class="category-badge">{category}</span>
                <h2 style="margin-top: 1rem;">{question}</h2>
            </div>
            """,
            unsafe_allow_html=True
        )

    @staticmethod
    def display_answer_options(options: list, key_suffix: str):
        """Display answer options in an improved layout"""
        selected_option = None
        
        # Create two columns for options
        col1, col2 = st.columns(2)
        
        # Display options A and B in first column
        with col1:
            for option in options[:2]:
                if st.button(
                    option,
                    key=f"{option}_{key_suffix}",
                    use_container_width=True,
                    type="secondary"
                ):
                    selected_option = option
        
        # Display options C and D in second column
        with col2:
            for option in options[2:]:
                if st.button(
                    option,
                    key=f"{option}_{key_suffix}",
                    use_container_width=True,
                    type="secondary"
                ):
                    selected_option = option
        
        return selected_option

    @staticmethod
    def display_grade_selector():
        """Display an improved grade level selector"""
        st.sidebar.markdown("### 📚 Grade Level")
        grade_level = st.sidebar.select_slider(
            "Choose your grade:",
            options=list(range(1, 13)),
            value=st.session_state.get('grade_level', 4),
            format_func=lambda x: f"Grade {x}",
            help="Slide to adjust the difficulty level of questions"
        )
        
        # Visual indicator of difficulty
        level_text = "Elementary" if grade_level <= 5 else "Middle" if grade_level <= 8 else "High"
        level_emoji = "🎈" if grade_level <= 5 else "🌟" if grade_level <= 8 else "🎓"
        
        st.sidebar.markdown(
            f"""
            <div style='text-align: center; padding: 1rem; background-color: white; border-radius: 0.5rem;'>
                <div style='font-size: 2rem;'>{level_emoji}</div>
                <div style='font-weight: bold; color: #1E88E5;'>{level_text} School</div>
                <div style='color: #666;'>Grade {grade_level}</div>
            </div>
            """,
            unsafe_allow_html=True
        )
        
        return grade_level

    @staticmethod
    def display_game_controls():
        """Display game control buttons"""
        col1, col2, space, col3 = st.columns([1, 1, 2, 1])
        
        with col1:
            next_question = st.button(
                "Next Question ➡️",
                type="primary",
                use_container_width=True
            )
            
        with col2:
            retry_question = st.button(
                "Retry Question 🔄",
                type="secondary",
                use_container_width=True
            )
            
        with col3:
            end_game = st.button(
                "End Game ⏹️",
                type="secondary",
                use_container_width=True
            )
            
        return next_question, retry_question, end_game

    @staticmethod
    def display_explanation(explanation: str):
        """Display the answer explanation in a card"""
        st.markdown(
            f"""
            <div style='background-color: #E3F2FD; padding: 1rem; border-radius: 0.5rem; margin-top: 1rem;'>
                <h3 style='color: #1E88E5; margin: 0;'>Explanation</h3>
                <p style='margin: 0.5rem 0 0 0;'>{explanation}</p>
            </div>
            """,
            unsafe_allow_html=True
        )

    @staticmethod
    def handle_end_game():
        """Display final score and option to restart the game."""
        try:
            st.markdown(
                """
                <div class="question-card">
                    <h2 style="color: #1E88E5; margin-bottom: 1rem;">🎮 Game Over!</h2>
                    <div style="margin-bottom: 1rem;">
                """,
                unsafe_allow_html=True
            )
            
            # Calculate statistics
            total_questions = st.session_state['total_questions']
            correct_answers = st.session_state['score']
            
            if total_questions > 0:
                accuracy = (correct_answers / total_questions) * 100
                avg_attempts = st.session_state['total_attempts'] / total_questions
            else:
                accuracy = 0
                avg_attempts = 0
                
            # Display final statistics
            col1, col2, col3 = st.columns(3)
            with col1:
                st.markdown(
                    f"""
                    <div class="stats-card">
                        <h3 style="margin:0; color: #1E88E5;">Total Questions</h3>
                        <h2 style="margin:0;">{total_questions}</h2>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
            
            with col2:
                st.markdown(
                    f"""
                    <div class="stats-card">
                        <h3 style="margin:0; color: #1E88E5;">Final Score</h3>
                        <h2 style="margin:0;">{correct_answers}</h2>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
                
            with col3:
                st.markdown(
                    f"""
                    <div class="stats-card">
                        <h3 style="margin:0; color: #1E88E5;">Accuracy</h3>
                        <h2 style="margin:0;">{accuracy:.1f}%</h2>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
                
            # Display average attempts
            st.markdown(
                f"""
                <div style='text-align: center; margin-top: 1rem;'>
                    <p style='color: #666;'>Average attempts per question: <strong>{avg_attempts:.1f}</strong></p>
                </div>
                """,
                unsafe_allow_html=True
            )
            
            # Thank you message
            st.markdown(
                """
                <div style='text-align: center; margin: 2rem 0;'>
                    <p style='color: #1E88E5; font-size: 1.2rem;'>
                        Thank you for playing the STRAUS Math and Science Trivia Game! 👏
                    </p>
                </div>
                """,
                unsafe_allow_html=True
            )
            
            # Restart button
            if st.button("Play Again 🔄", type="primary", use_container_width=True):
                SessionState.reset_game()
                st.rerun()
                
            st.markdown("</div></div>", unsafe_allow_html=True)
            
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
            
        # Setup page configuration and theme
        GameUI.setup_page()
        show_logout_button()
        
        # Display main header
        GameUI.display_header()
        
        logging.info("Starting application")
        
        # Initialize game components
        client = AnthropicClient.create()
        SessionState.initialize()
        question_generator = QuestionGenerator(client)
        game_logic = GameLogic(question_generator)
        
        # Sidebar components
        with st.sidebar:
            # Grade level selector
            grade_level = GameUI.display_grade_selector()
            
            # Update grade level if changed
            if grade_level != st.session_state['grade_level']:
                st.session_state['grade_level'] = grade_level
                st.session_state['current_question'] = None
                logging.info(f"Grade level changed to {grade_level}")
            
            st.markdown("---")
            
            # Display current session stats
            GameUI.display_stats_dashboard()

        # Handle game over state first
        if st.session_state.get('game_over', False):
            GameUI.handle_end_game()
            return

        # Display game controls
        next_question, retry_question, end_game = GameUI.display_game_controls()

        # Handle control actions
        if end_game:
            st.session_state['game_over'] = True
            logging.info("Game end requested")
            GameUI.handle_end_game()
            return

        if next_question:
            logging.info("New question requested")
            game_logic.set_new_question()

        if retry_question and not st.session_state['answered']:
            logging.info("Question retry requested")
            st.session_state['retry_mode'] = True

        # Initial question generation
        if st.session_state['current_question'] is None and not st.session_state['loading_question']:
            logging.info("Initial question generation")
            game_logic.set_new_question()

        # Display current question and handle answers
        if st.session_state['current_question']:
            # Display the question in a card
            GameUI.display_question(
                st.session_state['current_question'],
                st.session_state['category']
            )

            if not st.session_state['answered'] and not st.session_state['loading_question']:
                # Show attempts if in retry mode
                if st.session_state['retry_mode']:
                    st.markdown(
                        f"<div style='color: #666;'>Attempts so far: {st.session_state['current_attempts']}</div>",
                        unsafe_allow_html=True
                    )
                
                # Display answer options and handle selection
                selected_option = GameUI.display_answer_options(
                    st.session_state['options'],
                    key_suffix=f"attempt_{st.session_state['current_attempts']}"
                )
                
                # Process answer if selected
                if selected_option:
                    logging.info("Answer submission attempted")
                    game_logic.submit_answer(selected_option)

            # Show explanation after answering
            if st.session_state['answered']:
                GameUI.display_explanation(st.session_state['explanation'])

    except Exception as e:
        logging.error(f"Critical error in main function: {str(e)}")
        st.error("An unexpected error occurred in the application")


if __name__ == "__main__":
    main()