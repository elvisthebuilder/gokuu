import re

user_text = "[Photo Received: /home/afrifa-gilbert/Documents/Dev/goku/gokuu/uploads/photo_123.jpg] (System Action: The user just uploaded this file...)"
photo_pattern = r'\[Photo Received:\s*(.+?)\]'
photos = re.findall(photo_pattern, user_text)

print(f"Photos found: {photos}")
