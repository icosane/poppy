import os
import gzip
import struct
import sys
from PIL import Image

class SmeeDynamicEngineTool:
    MAGIC = b"EXT0"

    @classmethod
    def unpack(cls, input_path: str) -> str:
        """
        Dynamically extracts landscape pixel maps by calculating the exact trailing header size.
        """
        if input_path.lower().endswith(".ext.gz"):
            output_image_path = input_path[:-7] + ".png"
        else:
            output_image_path = os.path.splitext(input_path) + ".png"

        print(f"[*] Extracting texture payload from: {input_path}...")
        
        # 1. Expand the target compressed archive stream
        with gzip.open(input_path, 'rb') as f_gz:
            raw_data = f_gz.read()
            
        if len(raw_data) < 24:
            raise ValueError("Error: File payload is truncated or invalid.")

        magic = raw_data[:4]
        if magic != cls.MAGIC:
            raise ValueError(f"Error: Format signature failure. Got: {magic}")

        # Targeted extraction of the core widescreen dimension boundaries
        dim_v1, dim_v2 = struct.unpack("<II", raw_data[16:24])
        width = max(dim_v1, dim_v2)    # 1280 pixels
        height = min(dim_v1, dim_v2)   # 720 pixels
        
        expected_bytes = width * height * 4 # Exactly 3,686,400 bytes

        # Dynamically pinpoint the exact starting offset
        # Total file data size minus the pure image canvas size reveals the exact header width
        true_header_offset = len(raw_data) - expected_bytes
        print(f"[+] Dynamic Header Alignment Block Offset located: {true_header_offset} bytes.")

        # Slice the buffer precisely using the dynamic offset boundaries
        pixel_payload_clean = raw_data[true_header_offset:]

        if len(pixel_payload_clean) != expected_bytes:
            raise ValueError("Error: Internal buffer mapping validation failed.")

        # 2. Render out the unshifted widescreen image canvas
        img = Image.frombytes("RGBA", (width, height), pixel_payload_clean, "raw", "BGRA")
        img.save(output_image_path, "PNG")
        
        print(f"[+] Success! Clean asset written to: {output_image_path}")
        return output_image_path

    @classmethod
    def pack(cls, input_image_path: str, output_path: str = None) -> str:
        """
        Recompiles a landscape PNG image back into an engine-compliant .ext.gz asset block.
        """
        if not output_path:
            if input_image_path.lower().endswith(".png"):
                output_path = input_image_path[:-4] + ".ext.gz"
            else:
                output_path = os.path.splitext(input_image_path) + ".ext.gz"

        print(f"[*] Packing resource: {input_image_path}...")

        img = Image.open(input_image_path)
        if img.mode != "RGBA":
            img = img.convert("RGBA")
            
        width, height = img.size
        pixel_bytes = img.tobytes("raw", "BGRA")

        # Re-build custom container layout structural markers
        magic_block = cls.MAGIC
        alignment_spacer = b"\x00" * 12
        dimensions_block = struct.pack("<II", height, width) 
        
        # Calculate trailing metadata buffer remainder to maintain exact original binary footprint sizes
        # (Total header space requirement = 232 bytes total)
        header_padding_remainder = b"\x00" * (232 - (len(magic_block) + len(alignment_spacer) + len(dimensions_block)))
        
        full_payload = magic_block + alignment_spacer + dimensions_block + header_padding_remainder + pixel_bytes

        with gzip.open(output_path, 'wb', compresslevel=9) as f_gz:
            f_gz.write(full_payload)

        print(f"[+] Recompilation complete: {output_path}")
        return output_path


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] not in ["unpack", "pack"]:
        print("SMEE Widescreen Asset Tool CLI:")
        print("  Unpack: python ext_tool.py unpack <file.ext.gz>")
        print("  Pack:   python ext_tool.py pack   <file.png>")
        sys.exit(1)

    action = sys.argv[1]
    target_file = sys.argv[2]

    try:
        if action == "unpack":
            SmeeDynamicEngineTool.unpack(target_file)
        elif action == "pack":
            SmeeDynamicEngineTool.pack(target_file)
    except Exception as e:
        print(f"[-] Execution Error: {e}")
        sys.exit(1)
