import zipfile
from lxml import etree
import re
import os
import sys

# Find any EPUB in input folder
input_dir = "input"
epub_path = None

if os.path.exists(input_dir):
    files = [f for f in os.listdir(input_dir) if f.lower().endswith('.epub')]
    if files:
        epub_path = os.path.join(input_dir, files[0])

if not epub_path:
    print("FATAL: Could not find any EPUB file in input/ directory.")
    sys.exit(1)

print(f"Using EPUB: {epub_path}")

def normalize_text(text):
    if not text: return ""
    return re.sub(r'\s+', ' ', text).strip().lower()

with zipfile.ZipFile(epub_path, 'r') as z:
    try:
        # Pega qualquer arquivo que pareça ser o cap_001
        files = z.namelist()
        filename = next((f for f in files if "cap_001.xhtml" in f.lower()), None)
        
        if filename:
            print(f"--- Analisando {filename} ---")
            with z.open(filename) as f:
                content = f.read()
                tree = etree.HTML(content)
                
                # Full raw check
                raw_text = content.decode('utf-8', errors='ignore').lower()
                print(f"Raw 'topico' count: {raw_text.count('topico')}")
                print(f"Raw 'tópico' count: {raw_text.count('tópico')}")
                
                # Extracted text check
                all_text = " ".join(tree.xpath('//body//text()'))
                all_attr = " ".join(tree.xpath('//body//@title | //body//@aria-label | //body//@alt'))
                
                norm_text = normalize_text(all_text + " " + all_attr)
                
                print(f"Normalized content length: {len(norm_text)}")
                
                if "tópico" in norm_text:
                     print(f"FOUND 'tópico' {norm_text.count('tópico')} times.")
                     # Print all contexts
                     start = 0
                     for _ in range(min(5, norm_text.count('tópico'))):
                         idx = norm_text.find("tópico", start)
                         if idx == -1: break
                         print(f"Match #{_}: ...{norm_text[max(0, idx-20):min(len(norm_text), idx+50)]}...")
                         start = idx + 1
                else:
                    print("ABSENT: 'tópico' string not found in normalized text.")
                    
        else:
            print("cap_001.xhtml not found")

    except Exception as e:
        print(f"Error: {e}")
