#!/usr/bin/env python3
import os
import sys
import re
import argparse
from urllib.parse import urlparse

try:
    import qrcode
except ImportError:
    print("Error: The 'qrcode' library is not installed.")
    print("Please install it using: pip install qrcode[pil]")
    sys.exit(1)

def slugify(value):
    """
    Normalizes string, converts to lowercase, removes non-alphanumeric characters,
    and converts spaces to hyphens/underscores.
    """
    parsed = urlparse(value)
    name = parsed.netloc + parsed.path
    # Replace common non-alphanumeric characters with underscores
    name = re.sub(r'[^\w\s-]', '_', name).strip().lower()
    name = re.sub(r'[-\s_]+', '_', name)
    return name.strip('_')

def main():
    parser = argparse.ArgumentParser(
        description="Generate a high-quality QR code image from a link and save it to the output folder."
    )
    parser.add_argument(
        "url",
        nargs="?",
        help="The URL/link to encode in the QR code. If not provided, you will be prompted."
    )
    parser.add_argument(
        "-o", "--output",
        help="Output filename. If not provided, it will be generated based on the URL (e.g., qr_<slug>.png)."
    )
    parser.add_argument(
        "--fill",
        default="black",
        help="Color of the QR code modules/squares (default: black)"
    )
    parser.add_argument(
        "--back",
        default="white",
        help="Color of the QR code background (default: white)"
    )
    parser.add_argument(
        "--size",
        type=int,
        default=10,
        help="Box size of the QR code modules in pixels (default: 10)"
    )
    parser.add_argument(
        "--border",
        type=int,
        default=4,
        help="Border size in boxes (default: 4)"
    )

    args = parser.parse_args()

    # Get URL
    url = args.url
    if not url:
        try:
            url = input("Enter the link/URL for the QR code: ").strip()
        except KeyboardInterrupt:
            print("\nOperation cancelled.")
            sys.exit(1)
        if not url:
            print("Error: No URL provided.")
            sys.exit(1)

    # Determine workspace root and output directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if os.path.basename(script_dir) == 'scripts':
        workspace_root = os.path.dirname(script_dir)
    else:
        workspace_root = script_dir

    output_dir = os.path.join(workspace_root, 'output')
    os.makedirs(output_dir, exist_ok=True)

    # Determine output filename
    if args.output:
        filename = args.output
        if not filename.lower().endswith(('.png', '.jpg', '.jpeg', '.svg')):
            filename += '.png'
    else:
        slug = slugify(url)
        if not slug:
            slug = "qrcode"
        filename = f"qr_{slug}.png"

    dest_path = os.path.join(output_dir, filename)

    print(f"Generating QR code for: {url}")
    
    try:
        # Create QR code instance
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=args.size,
            border=args.border,
        )
        qr.add_data(url)
        qr.make(fit=True)

        # Generate image
        qr_img = qr.make_image(fill_color=args.fill, back_color=args.back)
        qr_img.save(dest_path)
        
        print(f"Success! QR code saved to:")
        print(f"  {os.path.abspath(dest_path)}")
        
    except Exception as e:
        print(f"Error generating QR code: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
