import os
import openai

def call_openai_llm(prompt, model="gpt-3.5-turbo", max_tokens=512, temperature=0.2):
    """
    Call the OpenAI ChatCompletion API with the given prompt and return the response text.
    Args:
        prompt (str): The prompt to send to the LLM.
        model (str): The OpenAI model to use (default: gpt-3.5-turbo).
        max_tokens (int): Maximum tokens in the response.
        temperature (float): Sampling temperature.
    Returns:
        str: The LLM's response text.
    Raises:
        Exception: If the API call fails or the response is invalid.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY environment variable not set.")
    openai.api_key = api_key
    response = openai.ChatCompletion.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return response.choices[0].message["content"] 