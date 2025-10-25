import os
import json
import re
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)

prompt = """What would be a fair base price in USD for an accountability agent service that helps track goals and predictions?
Consider the value provided and market rates.
Reply with ONLY an XML tag with the price like this: <price>X.XX</price>"""

prices = []

for i in range(3):
    print(f"Getting price estimate {i+1}/3...")

    completion = client.chat.completions.create(
        extra_headers={
            "HTTP-Referer": "http://localhost:8000",
            "X-Title": "Accountability Agent",
        },
        model="openai/gpt-5-mini",
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
    )

    response = completion.choices[0].message.content
    print(f"Response {i+1}: {response}")

    try:
        match = re.search(r'<price>([\d.]+)</price>', response)
        if match:
            price = float(match.group(1))
            prices.append(price)
            print(f"Parsed price: ${price}")
        else:
            print(f"No price tag found in response")
    except Exception as e:
        print(f"Error parsing response: {e}")

if prices:
    average_price = sum(prices) / len(prices)
    print(f"\nBase prices: ${prices}")
    print(f"Average base price: ${average_price:.2f}")
else:
    print("Failed to get any valid prices")
