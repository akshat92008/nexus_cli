from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.key_binding import KeyBindings

kb = KeyBindings()

@kb.add('enter')
def _(event):
    event.current_buffer.validate_and_handle()

@kb.add('escape', 'enter')
def _(event):
    event.current_buffer.insert_text('\n')

session = PromptSession(history=InMemoryHistory())

try:
    print("Type something and press Enter:")
    result = session.prompt(HTML('<ansicyan> ❯ </ansicyan>'), key_bindings=kb)
    print("Result:", repr(result))
except Exception as e:
    print("Error:", e)
