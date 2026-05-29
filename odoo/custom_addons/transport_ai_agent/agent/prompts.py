# -*- coding: utf-8 -*-
"""
Prompts système — multilingue (fr, en, ar)
La langue est détectée dans agent_core.py via language_detector.py
"""
from agent.language_detector import get_system_prompt

# Compatibilité ascendante — gardé pour import externe éventuel
SYSTEM_PROMPT = get_system_prompt("fr")
