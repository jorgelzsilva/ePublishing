import zipfile
import io
from PIL import Image
from colorama import Fore

def validate_image_sizes(epub_path, max_pixels=5600000):
    """
    Checks all images in the EPUB and returns a list of those exceeding max_pixels.
    """
    invalid_images = []
    
    try:
        with zipfile.ZipFile(epub_path, 'r') as z:
            image_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp', '.tiff')
            image_files = [f for f in z.namelist() if f.lower().endswith(image_extensions)]
            
            for img_path in image_files:
                # SVG doesn't have fixed pixel dimensions in the same way, usually ignored or handled differently
                if img_path.lower().endswith('.svg'):
                    continue
                    
                try:
                    with z.open(img_path) as img_file:
                        img_data = img_file.read()
                        with Image.open(io.BytesIO(img_data)) as img:
                            width, height = img.size
                            total_pixels = width * height
                            
                            if total_pixels > max_pixels:
                                invalid_images.append({
                                    "path": img_path,
                                    "width": width,
                                    "height": height,
                                    "pixels": total_pixels
                                })
                except Exception as e:
                    # If it's not a valid image or another error occurs, skip or report as error
                    # For now, we skip to focus on pixel count
                    continue
                    
        return invalid_images
    except Exception as e:
        print(f"{Fore.RED}    [!] Erro ao processar imagens: {e}")
        return []
