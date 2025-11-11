def translate_error(error_msg: str) -> str:
    """Translates technical error messages into user-friendly French explanations."""
    if not isinstance(error_msg, str):
        error_msg = str(error_msg)
    
    error_msg_lower = error_msg.lower()

    # Handle the generic "Unexpected error" wrapper by cleaning it and re-running translation
    if error_msg_lower.startswith("unexpected error:"):
        clean_error = error_msg[len("unexpected error:"):].strip()
        return translate_error(clean_error)

    if "follow-up success message not found" in error_msg_lower:
        return "Le message de confirmation du site n'est pas apparu à temps. Le site était peut-être trop lent ou une erreur inattendue s'est produite."
    if "timeout clicking follow order button" in error_msg_lower:
        return "Je n'ai pas réussi à cliquer sur le bouton pour copier l'ordre car le site était trop lent à charger."
    if "permanent error" in error_msg_lower:
        if "incorrect credentials" in error_msg_lower:
            return "Les identifiants de connexion pour ce compte sont incorrects. Le compte est ignoré."
        return "Une erreur permanente est survenue (ex: compte bloqué ou problème de validation de session). Ce compte sera ignoré jusqu'à correction."
    if "order already exists" in error_msg_lower or "exist" in error_msg_lower:
        return "L'ordre a déjà été copié sur ce compte précédemment."
    if "not logged in" in error_msg_lower:
        return "La session a expiré ou la connexion a échoué. Je n'ai pas pu accéder à la page de trading."
    
    # Fallback for other generic but common errors
    if "timeout" in error_msg_lower:
        return f"L'opération a expiré car le site a mis trop de temps à répondre."

    # Improved default fallback
    return f"Une erreur technique non répertoriée est survenue. Contactez le support avec cette information : \"{error_msg[:70]}\"..."
