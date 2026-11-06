import re

with open('templates/roommate/quiz.html', 'r', encoding='utf-8') as f:
    text = f.read()

text = re.sub(r'\s*<div class="option-icon">.*?</div>', '', text)
text = text.replace('font-size: 1.25rem;', 'font-size: 1rem;')
text = text.replace('font-size: 1.75rem;', 'font-size: 1.3rem;')
text = text.replace('padding: 1.5rem;', 'padding: 1rem 1.5rem;')

with open('templates/roommate/quiz.html', 'w', encoding='utf-8') as f:
    f.write(text)
print("Quiz updated successfully!")
