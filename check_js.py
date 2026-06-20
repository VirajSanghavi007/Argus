import re

with open('frontend/index.html', encoding='utf-8') as f:
    content = f.read()

start = content.find('<script>')
end   = content.rfind('</script>')
js    = content[start+8:end]

issues = []

# Bare identifiers on their own line outside comments
lines = js.split('\n')
in_block_comment = False
for i, line in enumerate(lines, 1):
    stripped = line.strip()
    if '/*' in stripped: in_block_comment = True
    if '*/' in stripped: in_block_comment = False; continue
    if in_block_comment: continue
    if stripped.startswith('//'): continue
    if re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', stripped):
        if stripped not in ('undefined','null','true','false','break','continue','return'):
            issues.append(f'JS line {i}: bare identifier outside comment: {stripped!r}')

# Check for obvious issues
for i, line in enumerate(lines, 1):
    if 'background:#fff' in line and 'body.dark' not in line and i < 430:
        issues.append(f'CSS line {i}: hardcoded #fff may not respond to dark mode: {line.strip()[:80]}')

if issues:
    for iss in issues:
        print('ISSUE:', iss)
else:
    print('No issues found in JS or CSS.')
