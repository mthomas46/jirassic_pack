import os
import openai
from dotenv import load_dotenv
import yaml
import asyncio
from concurrent.futures import ThreadPoolExecutor

def call_openai_llm(prompt, model="gpt-3.5-turbo", max_tokens=512, temperature=0.2, response_format=None):
    """
    Call the OpenAI ChatCompletion API with the given prompt and return the response text.
    Tries to load the API key from the environment, .env file, or jirassicpack/config.yaml.
    Args:
        prompt (str): The prompt to send to the LLM.
        model (str): The OpenAI model to use (default: gpt-3.5-turbo).
        max_tokens (int): Maximum tokens in the response.
        temperature (float): Sampling temperature.
        response_format (str): The format of the response.
    Returns:
        str: The LLM's response text.
    Raises:
        Exception: If the API key is not found or the API call fails.
    """
    # Load .env if present
    load_dotenv()
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        # Try to load from jirassicpack/config.yaml
        try:
            with open("jirassicpack/config.yaml") as f:
                config = yaml.safe_load(f)
                api_key = config.get("openai", {}).get("api_key")
        except Exception:
            pass
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set in environment, .env, or jirassicpack/config.yaml.")
    client = openai.OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=temperature,
        response_format=response_format,
    )
    return response.choices[0].message.content 

def call_openai_llm_threaded(prompt, model="gpt-3.5-turbo", max_tokens=512, temperature=0.2, executor=None):
    """Run call_openai_llm in a threadpool for multithreading."""
    loop = asyncio.get_event_loop()
    if executor is None:
        executor = ThreadPoolExecutor()
    return loop.run_in_executor(executor, call_openai_llm, prompt, model, max_tokens, temperature)

async def call_openai_llm_async(prompt, model="gpt-3.5-turbo", max_tokens=512, temperature=0.2, response_format=None):
    """Async version of call_openai_llm using openai.AsyncOpenAI."""
    load_dotenv()
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        try:
            with open("jirassicpack/config.yaml") as f:
                config = yaml.safe_load(f)
                api_key = config.get("openai", {}).get("api_key")
        except Exception:
            pass
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set in environment, .env, or jirassicpack/config.yaml.")
    client = openai.AsyncOpenAI(api_key=api_key)
    response = await client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=temperature,
        response_format=response_format,
    )
    return response.choices[0].message.content 