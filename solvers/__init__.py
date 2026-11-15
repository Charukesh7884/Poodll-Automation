# Solvers package for Moodle / Poodll / H5P activities
from solvers.readaloud_solver import ReadAloudSolver
from solvers.solo_solver import SoloSolver
from solvers.wordcards_solver import WordcardsSolver
from solvers.hvp_solver import HvpSolver
from solvers.quiz_solver import QuizSolver
from solvers.activity_tracker import ActivityTracker

__all__ = [
    "ReadAloudSolver",
    "SoloSolver",
    "WordcardsSolver",
    "HvpSolver",
    "QuizSolver",
    "ActivityTracker",
]
