import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)

completion = client.chat.completions.create(
    extra_headers={
        "HTTP-Referer": "http://localhost:8000",
        "X-Title": "Accountability Agent",
    },
    model="z-ai/glm-4.5-air:free",
    messages=[
        {
            "role": "user",
            "content": "Say hi. Reply with only one word.",
        }
    ],
)

print(completion.choices[0].message.content)
