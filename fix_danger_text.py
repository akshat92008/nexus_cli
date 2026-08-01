import re

with open("new_execute.py", "r") as f:
    content = f.read()

old_str = """        elif safety_check and safety_check.level == SafetyLevel.DANGEROUS and not _user_confirmed:
            confirmation_id = self._queue_confirmation(
                name=name,
                args=pending_args,
                safety_check=safety_check,
                edit_confirmed=_edit_confirmed,
            )
            return (
                "⏸️ PENDING_CONFIRMATION "
                f"[{confirmation_id}]: {safety_check.reason}. "
                f"Enter /confirm {confirmation_id} or /cancel {confirmation_id}.",
                False,
            )"""

new_str = """        elif safety_check and safety_check.level == SafetyLevel.DANGEROUS and not _user_confirmed:
            confirmation_id = self._queue_confirmation(
                name=name,
                args=pending_args,
                safety_check=safety_check,
                edit_confirmed=_edit_confirmed,
            )
            return (
                "⏸️ PENDING_CONFIRMATION "
                f"[{confirmation_id}]: {safety_check.reason}. "
                "This operation was not executed. Review the exact operation, then "
                f"enter /confirm {confirmation_id} or /cancel {confirmation_id}.\\n"
                f"{safety_check.details}",
                False,
            )"""

content = content.replace(old_str, new_str)
with open("new_execute.py", "w") as f:
    f.write(content)

