# utils.py
from PyPDF2 import PdfReader
import io
import json

def extract_text_from_pdf(pdf_file_stream):
    """
    Extracts text from a PDF file stream.

    Args:
        pdf_file_stream: A file-like object (e.g., from request.files).

    Returns:
        str: The extracted text, or None if extraction fails.
    """
    try:
        pdf_file_stream.seek(0) # Ensure stream position is at the beginning
        reader = PdfReader(pdf_file_stream)
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n" # Add newline between pages
        print(f"Extracted {len(text)} characters from PDF.")
        return text if text else None
    except Exception as e:
        print(f"Error extracting text from PDF: {e}")
        return None

