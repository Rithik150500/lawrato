from flask import Flask, render_template, request, jsonify
import anthropic
import os

# Initialize Flask application
app = Flask(__name__)

# Initialize the Anthropic client
# Important: You should move your API key to an environment variable for security
# For now, I'm using the key from your original file, but please set it as an environment variable
client = anthropic.Anthropic(
    api_key=os.environ.get("ANTHROPIC_API_KEY")
)

def make_initial_research_call(user_prompt):
    """
    This function performs the actual legal research by calling the Claude API
    with web search enabled. It takes the user's question and returns comprehensive
    case law research.
    
    Args:
        user_prompt: The legal question(s) from the user
    
    Returns:
        The complete message response object from the API
    """
    # Build the system instructions that tell Claude how to act as a legal researcher
    system_instructions = f"""You are a legal research assistant specializing in Indian case law. Your task is to find relevant recent or landmark cases from Indian courts that relate to the legal questions provided.

Here are the legal questions you need to research:

<legal_questions>
{user_prompt}
</legal_questions>

For each legal question, you need to:

1. Find applicable recent or landmark cases from Indian courts (Supreme Court, High Courts, etc.)
2. For each relevant case, provide:
   - The complete case title and citation
   - A concise summary of the judgment
   - A key paragraph from the final judgment

Instructions:
- Focus on cases that directly address the legal issues raised in each question
- Prioritize recent cases (last 10-15 years) unless landmark older cases are more relevant
- Ensure your case citations are accurate and complete
- Keep summaries concise but comprehensive enough to understand the court's reasoning
- Quote actual text from judgment paragraphs when possible

Before providing your final response, work through each legal question systematically in <legal_research_planning> tags inside your thinking block. In your planning:
- Break down each question to identify the core legal issues and sub-issues
- Identify the specific areas of Indian law that are most relevant (family law, criminal law, civil law, constitutional law, etc.)
- Consider what types of precedents would be most helpful (Supreme Court landmark cases, recent High Court decisions, etc.)
- Note key legal principles and doctrines that should guide your research
- Think about different angles or interpretations of each question that might require different case law
- Ensure you're systematically addressing all the questions provided
It's OK for this section to be quite long.

Your final response should consist only of the structured case law research organized by legal question, and should not duplicate or rehash any of the planning work you did in the thinking block."""
    
    # Make the API call using the beta endpoint with web search enabled
    # This allows Claude to search the web for recent case law information
    message = client.beta.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=20000,
        temperature=1,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": system_instructions
                    }
                ]
            }
        ],
        tools=[
            {
                "name": "web_search",
                "type": "web_search_20250305"
            }
        ],
        thinking={
            "type": "enabled",
            "budget_tokens": 16000
        },
        betas=["web-search-2025-03-05"]
    )
    
    return message


def make_followup_call(user_prompt, first_message, followup_prompt):
    """
    This function makes a follow-up call to refine or expand on the initial research.
    It maintains the conversation context so Claude can build upon its previous work.
    
    Args:
        user_prompt: The original legal question(s) from the first call
        first_message: The complete response object from the first API call
        followup_prompt: The user's follow-up question (in this case, same as user_prompt)
    
    Returns:
        The complete message response object from the API
    """
    # Build the conversation history by including the first user message,
    # the complete assistant response, and then the new follow-up question
    messages = [
        # First turn: original user question
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": user_prompt
                }
            ]
        },
        # Second turn: assistant's complete response from the first call
        {
            "role": "assistant",
            "content": first_message.content
        },
        # Third turn: user's follow-up question (same as original for refinement)
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": followup_prompt
                }
            ]
        }
    ]
    
    # Make the API call with the full conversation history
    # We use "CONCISE" system prompt to get a more focused response
    message = client.beta.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=20000,
        temperature=1,
        system="STYLE: CONCISE, EXPLANATORY. You are a legal assistant specializing in Indian case law",
        messages=messages,
        thinking={
            "type": "enabled",
            "budget_tokens": 16000
        },
    )
    
    return message


def extract_text_from_response(message):
    """
    Helper function to extract just the text content from a message response.
    The API returns content as a list of blocks, which might include thinking
    blocks and text blocks. This function pulls out just the text that we want
    to show to the user.
    
    Args:
        message: The API response object
    
    Returns:
        A string containing all the text content (without thinking blocks)
    """
    text_parts = []
    for block in message.content:
        if block.type == "text":
            text_parts.append(block.text)
    return "\n\n".join(text_parts)


@app.route('/')
def index():
    """
    Route handler for the home page.
    Simply renders the HTML template we created.
    """
    return render_template('26101718.html')


@app.route('/research', methods=['POST'])
def research():
    """
    Route handler for the research endpoint.
    This is called when the user submits the form. It receives the legal question,
    performs the research using the two-step process, and returns the results.
    
    Returns:
        JSON response containing either the research results or an error message
    """
    try:
        # Get the question from the POST request
        data = request.get_json()
        question = data.get('question', '').strip()
        
        # Validate that we actually got a question
        if not question:
            return jsonify({'error': 'Please provide a legal question.'}), 400
        
        print(f"\n{'='*80}")
        print(f"Received research request: {question[:100]}...")
        print(f"{'='*80}\n")
        
        # Step 1: Make the initial research call
        # This is where Claude searches for relevant case law
        print("Step 1: Making initial research call...")
        first_response = make_initial_research_call(question)
        
        # Step 2: Make the follow-up call with conversation history
        # This helps refine and structure the response better
        print("Step 2: Making follow-up call for refinement...")
        second_response = make_followup_call(question, first_response, question)
        
        # Extract the final text response (without thinking blocks)
        final_result = extract_text_from_response(second_response)
        
        print("Research complete! Sending results to user.\n")
        
        # Return the results as JSON
        return jsonify({
            'result': final_result,
            'success': True
        })
        
    except Exception as e:
        # If anything goes wrong, log the error and return it to the user
        print(f"Error occurred: {str(e)}")
        return jsonify({
            'error': f'An error occurred while processing your request: {str(e)}',
            'success': False
        }), 500


if __name__ == '__main__':
    # Run the Flask development server
    # Set debug=True to see detailed error messages during development
    # In production, you should set debug=False and use a proper WSGI server
    print("\n" + "="*80)
    print("INDIAN LEGAL RESEARCH ASSISTANT - WEB VERSION")
    print("="*80)
    print("\nStarting server on http://localhost:5000")
    print("Press Ctrl+C to stop the server\n")
    

    app.run(debug=True, host='0.0.0.0', port=5000)
