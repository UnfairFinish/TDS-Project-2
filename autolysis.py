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

import numpy as np
from scipy.stats import skew, kurtosis, ttest_ind, chi2_contingency

def analyze_data(df):
    """
    Perform detailed exploratory data analysis (EDA) on the dataset.
    
    Parameters:
    - df (pd.DataFrame): The dataset to analyze.
    
    Returns:
    - dict: A dictionary containing detailed analysis results.
    """
    numeric_df = df.select_dtypes(include=['number'])
    categorical_df = df.select_dtypes(include=['object', 'category'])
    datetime_columns = df.select_dtypes(include=['datetime'])

    # Summary statistics
    summary = df.describe(include='all').to_dict()

    # Skewness and kurtosis
    if not numeric_df.empty:
        summary['skewness'] = numeric_df.apply(skew, nan_policy='omit').to_dict()
        summary['kurtosis'] = numeric_df.apply(kurtosis, nan_policy='omit').to_dict()

    # Outlier detection
    outliers = {}
    for col in numeric_df.columns:
        Q1 = numeric_df[col].quantile(0.25)
        Q3 = numeric_df[col].quantile(0.75)
        IQR = Q3 - Q1
        outliers[col] = {
            'lower_bound': Q1 - 1.5 * IQR,
            'upper_bound': Q3 + 1.5 * IQR,
            'outlier_count': ((numeric_df[col] < Q1 - 1.5 * IQR) | (numeric_df[col] > Q3 + 1.5 * IQR)).sum()
        }

    # Correlation matrix
    correlation = numeric_df.corr().to_dict() if not numeric_df.empty else {}

    # Missing values
    missing_values = df.isnull().sum().to_dict()

    # Examples of data
    examples = df.head(5).to_dict()

    # Categorical value counts
    categorical_analysis = {}
    for col in categorical_df.columns:
        counts = df[col].value_counts()
        categorical_analysis[col] = {
            'value_counts': counts.to_dict(),
            'unique_values': counts.index.tolist()
        }

    # Statistical tests (if categorical and numeric variables are present)
    statistical_tests = {}
    if not numeric_df.empty and not categorical_df.empty:
        for cat_col in categorical_df.columns:
            for num_col in numeric_df.columns:
                grouped = [numeric_df[num_col][df[cat_col] == cat].dropna() for cat in df[cat_col].unique()]
                if len(grouped) > 1:
                    try:
                        stat, p_value = ttest_ind(*grouped, equal_var=False)
                        statistical_tests[f"{cat_col} vs {num_col}"] = {"t-stat": stat, "p-value": p_value}
                    except Exception as e:
                        statistical_tests[f"{cat_col} vs {num_col}"] = {"error": str(e)}

    # Chi-squared test for categorical variables
    chi_squared_results = {}
    for col1 in categorical_df.columns:
        for col2 in categorical_df.columns:
            if col1 != col2:
                contingency = pd.crosstab(df[col1], df[col2])
                chi2, p, dof, expected = chi2_contingency(contingency, correction=False)
                chi_squared_results[f"{col1} vs {col2}"] = {"chi2": chi2, "p-value": p, "dof": dof}

    # Final analysis dictionary
    analysis = {
        'summary_statistics': summary,
        'outliers': outliers,
        'correlation': correlation,
        'missing_values': missing_values,
        'examples': examples,
        'categorical_analysis': categorical_analysis,
        'statistical_tests': statistical_tests,
        'chi_squared_results': chi_squared_results,
        'column_types': df.dtypes.astype(str).to_dict(),
    }

    return analysis


def visualize_data(df, max_distributions=None):
    """
    Generate and save enhanced visualizations with detailed titles and labels.
    
    Parameters:
    - df (pd.DataFrame): DataFrame to visualize.
    - max_distributions (int): Maximum number of distribution plots. Default is None (all numeric columns).
    
    Returns:
    - list: List of paths to saved image files.
    """
    sns.set(style="whitegrid")
    output_images = []

    # Correlation Heatmap
    numeric_df = df.select_dtypes(include=['number'])
    if not numeric_df.empty:
        plt.figure(figsize=(10, 8))
        correlation = numeric_df.corr()
        sns.heatmap(correlation, annot=True, cmap="coolwarm", fmt=".2f", linewidths=0.5)
        plt.title("Correlation Heatmap")
        plt.xlabel("Features")
        plt.ylabel("Features")
        heatmap_path = "visualizations/correlation_heatmap.png"
        os.makedirs(os.path.dirname(heatmap_path), exist_ok=True)
        plt.savefig(heatmap_path, bbox_inches="tight")
        output_images.append(heatmap_path)
        plt.close()

    # Distribution Plots
    if max_distributions is None:
        columns_to_plot = numeric_df.columns
    else:
        columns_to_plot = numeric_df.columns[:max_distributions]

    for column in columns_to_plot:
        plt.figure(figsize=(8, 6))
        sns.histplot(df[column].dropna(), kde=True, color='blue', bins=30)
        plt.title(f'Distribution of {column}')
        plt.xlabel(column)
        plt.ylabel("Frequency")
        plt.legend(labels=["Distribution"])
        dist_path = f'visualizations/{column}_distribution.png'
        plt.savefig(dist_path, bbox_inches="tight")
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
