"""Extract a clean transcript from a Teams meeting docx (unpacked)."""
import re
import sys
from xml.etree import ElementTree as ET

NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}

def extract(path):
    tree = ET.parse(path)
    root = tree.getroot()
    out = []
    for p in root.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p'):
        parts = []
        for node in p.iter():
            tag = node.tag.split('}')[-1]
            if tag == 't':
                parts.append(node.text or '')
            elif tag == 'br':
                parts.append('\n')
        text = ''.join(parts).strip()
        if text:
            out.append(text)
    return '\n'.join(out)

if __name__ == '__main__':
    print(extract(sys.argv[1]))
