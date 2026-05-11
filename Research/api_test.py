"""
Simple script to test GROQ API keys by making one `ChatGroq.invoke` call per key.
Run from the `Research` folder (where your project and .env live):

python api_test.py

It prints whether each key returns a response or an error.
"""
from dotenv import load_dotenv
import os
import traceback

load_dotenv()

from langchain_groq import ChatGroq

KEYS = {
    'GROQ_API_KEY':""
}

PROMPT = [
    {"role": "system", "content": "You are a tiny test assistant."},
    {"role": "user", "content": "Respond with exactly: OK"}
]


def test_key(name, key):
    print('\n' + '='*60)
    print(f"Testing {name} -> {'(missing)' if not key else key}")
    if not key:
        print(f"{name} not set; skipping")
        return

    try:
        client = ChatGroq(model="llama-3.3-70b-versatile", api_key=key, temperature=0)
        print('Instantiated ChatGroq client, invoking...')
        resp = client.invoke(PROMPT)
        # Try to read common response attributes
        content = None
        if hasattr(resp, 'content'):
            content = resp.content
        elif isinstance(resp, dict) and 'content' in resp:
            content = resp['content']
        else:
            content = str(resp)
        print('Success — response (truncated):', (content or '')[:400])
    except Exception as e:
        print('Error invoking LLM with this key:')
        traceback.print_exc()


if __name__ == '__main__':
    print('Starting GROQ API keys test')
    for name, key in KEYS.items():
        test_key(name, key)
    print('\nFinished tests')
