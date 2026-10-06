import re


def clean_text(text):
    """
    Cleans a text description for NLP processing.
    """

    # Convert to lowercase
    text = text.lower()

    # Replace hyphens with spaces
    text = text.replace("-", " ")

    # Remove punctuation and special characters
    text = re.sub(r"[^a-zA-Z0-9\s]", "", text)

    # Remove extra spaces
    text = re.sub(r"\s+", " ", text).strip()

    return text


# Test the function
if __name__ == "__main__":

    example = "I lost my Navy-Blue Backpack near the University Library!!!"

    cleaned = clean_text(example)

    print("Original:")
    print(example)

    print("\nCleaned:")
    print(cleaned)