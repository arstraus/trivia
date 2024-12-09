# STRAUS Math and Science Trivia Game

An educational trivia game powered by Claude AI that generates grade-appropriate questions across various STEM subjects.

## Features

- Dynamic question generation using Claude AI
- Grade level selection (1-12)
- Multiple STEM categories including Science, Technology, Engineering, Math, Space, Animals, Nature, Geography, and Biology
- Score tracking and performance statistics
- Secure login system
- Multiple attempts allowed for each question

## Setup

1. Clone the repository:
```bash
git clone https://github.com/arstraus/trivia.git
cd trivia
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up your environment:
   - Create a `.env` file in the root directory
   - Add your Anthropic API key: `ANTHROPIC_API_KEY=your-key-here`

4. Set up Streamlit secrets:
   - Create `.streamlit/secrets.toml`
   - Add your credentials (follow template provided in deployment)

## Running Locally

```bash
streamlit run app.py
```

## Deployment

This app is configured for deployment on Streamlit Cloud. Required secrets:
- Anthropic API key
- Authentication credentials

## Login Credentials

Default login:
- Username: admin
- Contact administrator for password

## Technologies Used

- Python
- Streamlit
- Anthropic's Claude AI
- Python-dotenv

## Security Notes

- Secure password hashing implemented
- Environment variables for sensitive data
- Authentication required for access