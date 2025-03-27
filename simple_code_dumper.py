# simple_code_dumper.py
import os

FILES_TO_DUMP = [
    'api_handler.py',
    'app.py',
    'config.py',
    'models.py',
    'forms.py',
    'encryption.py',
    'utils.py',
    'api_handler.py',
    'routes/main.py',
    'routes/auth.py',
    'routes/settings.py',
    'routes/tests.py',
    'templates/settings/account.html',
    'templates/tests/generate.html',
]

OUTPUT_FILE = 'code_dump.txt'

print(f"Dumping code to {OUTPUT_FILE}...")

with open(OUTPUT_FILE, 'w', encoding='utf-8') as outfile:
    for filepath in FILES_TO_DUMP:
        outfile.write(f"\n{'='*10} START: {filepath} {'='*10}\n\n")
        try:
            with open(filepath, 'r', encoding='utf-8') as infile:
                outfile.write(infile.read())
        except FileNotFoundError:
            outfile.write(f"!!! File not found: {filepath} !!!\n")
        except Exception as e:
            outfile.write(f"!!! Error reading {filepath}: {e} !!!\n")
        outfile.write(f"\n{'='*10} END: {filepath} {'='*10}\n")

print("Done.")

# To run: python simple_code_dumper.py
# Then copy content from code_dump.txt