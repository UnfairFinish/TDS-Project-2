# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pandas>=2.0.0,<3.0.0",
#     "seaborn>=0.12.0,<0.14.0",
#     "matplotlib>=3.7.0,<3.9.0",
#     "kiwisolver>=1.4.4,<1.5.0",
#     "pyparsing>=3.0.0,<3.1.0",  # Add compatible version range for pyparsing
#     "httpx>=0.25.0,<1.0.0",
#     "chardet>=5.1.0,<6.0.0",
#     "tenacity>=8.2.0,<9.0.0"
# ]
# ///



import os
import sys
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import httpx
import chardet
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Constants
API_URL = "https://aiproxy.sanand.workers.dev/openai/v1/chat/completions"
AIPROXY_TOKEN = os.getenv("AIPROXY_TOKEN")  # Token via environment variable

def load_data(file_path, max_rows=100):
    """Load a subset of CSV data with encoding detection to speed up processing."""
    try:
        with open(file_path, 'rb') as f:
            result = chardet.detect(f.read())
        encoding = result['encoding']
        return pd.read_csv(file_path, encoding=encoding, nrows=max_rows)  # Load only the first `max_rows`
    except Exception as e:
        print(f"Error loading file: {e}")
        sys.exit(1)

def analyze_data(df):
    """Perform basic data analysis on a subset of the data."""
    numeric_df = df.select_dtypes(include=['number'])
    datetime_columns = df.select_dtypes(include=['datetime'])
    non_numeric_df = df.select_dtypes(exclude=['number', 'datetime'])

    # Summary statistics for a subset
    summary = df.describe(include='all').to_dict()
    if not datetime_columns.empty:
        for col in datetime_columns:
            summary[col] = {
                'min': df[col].min(),
                'max': df[col].max(),
                'unique': df[col].nunique()
            }

    analysis = {
        'summary': summary,
        'missing_values': df.isnull().sum().to_dict(),
        'correlation': numeric_df.corr().to_dict(),
        'examples': df.head(5).to_dict(),
        'column_types': df.dtypes.astype(str).to_dict(),
    }

    return analysis

def visualize_data(df):
    """Generate and save simplified visualizations."""
    sns.set(style="whitegrid")
    output_images = []

    # Correlation Heatmap
    numeric_df = df.select_dtypes(include=['number'])
    if not numeric_df.empty:
        plt.figure(figsize=(8, 6))  # Adjust size for quicker rendering
        correlation = numeric_df.corr()
        sns.heatmap(correlation, annot=True, cmap="coolwarm", fmt=".2f", linewidths=0.5)
        plt.title("Correlation Heatmap")
        heatmap_path = "correlation_heatmap.png"
        plt.savefig(heatmap_path)
        output_images.append(heatmap_path)
        plt.close()

    # Limit the number of distribution plots to the first 3 numeric columns
    for column in numeric_df.columns[:3]:  # Only plot up to 3 columns
        plt.figure()
        sns.histplot(df[column].dropna(), kde=True, color='blue')
        plt.title(f'Distribution of {column}')
        dist_path = f'{column}_distribution.png'
        plt.savefig(dist_path)
        output_images.append(dist_path)
        plt.close()

    return output_images

# Retry settings for faster failure
@retry(
    stop=stop_after_attempt(3),  # Retry up to 3 times
    wait=wait_exponential(multiplier=1, min=2, max=5),  # Exponential backoff (2s, 4s, 5s)
    retry=retry_if_exception_type(httpx.RequestError)  # Retry only on HTTP request errors
)
def generate_narrative(analysis, images):
    """Generate narrative using LLM with retries on failure."""
    headers = {
        'Authorization': f'Bearer {os.getenv("AIPROXY_TOKEN")}',
        'Content-Type': 'application/json'
    }
    prompt = f"Provide a detailed analysis based on the following data summary: {analysis} and these images: {images}"
    data = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": prompt}]
    }
    try:
        response = httpx.post(API_URL, headers=headers, json=data, timeout=60.0) 
        response.raise_for_status()  # Raise exception for HTTP errors
        return response.json()['choices'][0]['message']['content']
    except httpx.HTTPStatusError as e:
        print(f"HTTP error occurred: {e.response.status_code} - {e.response.text}")
        raise  # Allow tenacity to handle retries
    except httpx.RequestError as e:
        print(f"Request error occurred: {e}")
        raise  # Allow tenacity to handle retries
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        raise  # Allow tenacity to handle retries

def save_readme(narrative, images):
    """Save the narrative and embed images in README.md."""
    with open('README.md', 'w') as f:
        f.write("# Automated Data Analysis Report\n\n")
        f.write(narrative + "\n\n")
        for image in images:
            f.write(f"![{image}]({image})\n")

def main(file_path):
    """Main function to load data, analyze, visualize, and generate report."""
    df = load_data(file_path)
    analysis = analyze_data(df)
    images = visualize_data(df)
    narrative = generate_narrative(analysis, images)
    save_readme(narrative, images)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python autolysis.py <dataset.csv>")
        sys.exit(1)
    main(sys.argv[1])
