import fitz  # PyMuDF
import os
import re

def pdf_to_markdown(pdf_path, output_path=None):
    """
    Convert PDF to Markdown format
    
    Args:
        pdf_path (str): Path to the PDF file
        output_path (str): Path for the output Markdown file (optional)
    """
    
    # Open the PDF
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        print(f"Error opening PDF: {e}")
        return
    
    # If no output path specified, create one based on PDF name
    if output_path is None:
        base_name = os.path.splitext(os.path.basename(pdf_path))[0]
        output_path = f"{base_name}.md"
    
    markdown_content = []
    
    # Process each page
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        
        # Extract text
        text = page.get_text()
        
        if text.strip():  # Only add non-empty pages
            # Clean up the text
            text = clean_text(text)
            
            # Add page separator (optional)
            if page_num > 0:
                markdown_content.append("\n---\n")
            
            markdown_content.append(f"## Page {page_num + 1}\n\n")
            markdown_content.append(text)
            markdown_content.append("\n\n")
    
    # Write to markdown file
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(''.join(markdown_content))
        print(f"Successfully converted PDF to Markdown: {output_path}")
    except Exception as e:
        print(f"Error writing markdown file: {e}")
    
    # Close the PDF
    doc.close()

def clean_text(text):
    """
    Clean and format text for better markdown output
    """
    # Remove excessive whitespace
    text = re.sub(r'\n\s*\n', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    
    # Try to identify headers (lines that are all caps or have specific patterns)
    lines = text.split('\n')
    cleaned_lines = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Check if line might be a header (all caps, short, etc.)
        if (len(line) < 100 and 
            (line.isupper() or 
             re.match(r'^\d+\.?\s+[A-Z]', line) or
             re.match(r'^[A-Z][A-Z\s]+$', line))):
            cleaned_lines.append(f"### {line}")
        else:
            cleaned_lines.append(line)
    
    return '\n\n'.join(cleaned_lines)

def main():
    """
    Main function to run the converter
    """
    print("PDF to Markdown Converter")
    print("-" * 30)
    
    # Get PDF file path from user
    pdf_path = input("Enter the path to your PDF file: ").strip().strip('"')
    
    # Check if file exists
    if not os.path.exists(pdf_path):
        print("Error: PDF file not found!")
        return
    
    # Get output path (optional)
    output_path = input("Enter output path for Markdown file (press Enter for default): ").strip()
    if not output_path:
        output_path = None
    
    # Convert PDF to Markdown
    pdf_to_markdown(pdf_path, output_path)

if __name__ == "__main__":
    main()