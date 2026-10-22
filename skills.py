"""
skills.py — skill normalisation and extraction

Why this exists
---------------
The old skill-gap check treated a job skill as "matched" if ANY single word of
it appeared in the user's profile text (so "Machine Learning" matched on the
word "machine", and the text included goals/resume prose). This module
compares *normalised skills* instead:

  normalize_skill("JS")            -> "javascript"
  normalize_skill("Reactjs")       -> "react"
  parse_skill_list("Python, ML")   -> {"python", "machine learning"}
  extract_skills_from_text(...)    -> skills found in free text (resume/goals)
"""
import re

# alias (lowercase) -> canonical (lowercase)
ALIASES = {
    "js": "javascript", "java script": "javascript", "ecmascript": "javascript",
    "ts": "typescript",
    "ml": "machine learning", "machine-learning": "machine learning",
    "dl": "deep learning", "deep-learning": "deep learning",
    "natural language processing": "nlp",
    "cv": "computer vision",
    "reactjs": "react", "react.js": "react", "react basics": "react",
    "node": "node.js", "nodejs": "node.js", "node js": "node.js",
    "vue": "vue.js", "vuejs": "vue.js",
    "angularjs": "angular",
    "expressjs": "express", "express.js": "express",
    "postgres": "postgresql", "psql": "postgresql",
    "mongo": "mongodb", "mssql": "sql server", "ms sql": "sql server",
    "py": "python", "basic python": "python", "python3": "python",
    "golang": "go",
    "k8s": "kubernetes", "tf": "tensorflow",
    "sklearn": "scikit-learn", "scikit learn": "scikit-learn", "scikitlearn": "scikit-learn",
    "html5": "html", "css3": "css",
    "rest": "rest apis", "rest api": "rest apis", "restful": "rest apis",
    "restful api": "rest apis", "restful apis": "rest apis", "apis": "rest apis",
    "api": "rest apis",
    "oracle db": "oracle", "oracle database": "oracle",
    "google cloud": "gcp", "google cloud platform": "gcp",
    "amazon web services": "aws",
    "powerbi": "power bi", "ms excel": "excel", "microsoft excel": "excel",
    "ci cd": "ci/cd", "cicd": "ci/cd",
    "spring": "spring boot", "springboot": "spring boot",
    "ux": "ux design", "ui/ux": "ux design",
    "seo": "seo", "smart contract": "smart contracts",
    "web3": "web3.js", "web3js": "web3.js",
    "object oriented programming": "oop", "object-oriented programming": "oop",
}

# Words that are real skills in the dataset but also ordinary English / too short
# to trust when scanning FREE TEXT. They are still honoured when they appear in
# the structured comma-separated "skills" field.
AMBIGUOUS = {
    "c", "go", "can", "sem", "liquid", "operations", "policy", "content",
    "research", "security", "marketing", "metadata", "cloud", "architecture",
    "animation", "branding", "networking", "analytics", "communication",
    "compliance", "backup", "assembly", "unity", "sas", "ats", "swift",
    "express", "spring", "ros", "ml", "oop",
}


def normalize_skill(s: str) -> str:
    s = re.sub(r"\s+", " ", str(s).strip().lower()).strip(" .;:-")
    return ALIASES.get(s, s)


def parse_skill_list(text: str) -> set:
    """Parse a comma/semicolon/newline separated skills field."""
    if not text:
        return set()
    out = set()
    for part in re.split(r"[,;\n|]+", str(text)):
        n = normalize_skill(part)
        if n:
            out.add(n)
    return out


class SkillExtractor:
    """Finds known skills inside free text (resume, goals)."""

    def __init__(self, vocabulary):
        vocab = {normalize_skill(v) for v in vocabulary}
        # include alias surface forms that map into the vocabulary
        surface = {v for v in vocab}
        for alias, canon in ALIASES.items():
            if canon in vocab:
                surface.add(alias)
        surface = {t for t in surface if t not in AMBIGUOUS and len(t) >= 2}
        self._canon = {t: normalize_skill(t) for t in surface}
        terms = sorted(surface, key=len, reverse=True)
        pattern = "|".join(re.escape(t) for t in terms)
        self._rx = re.compile(
            r"(?<![A-Za-z0-9+#])(" + pattern + r")(?![A-Za-z0-9+#])", re.IGNORECASE
        ) if terms else None

    def extract(self, text: str) -> set:
        if not text or not self._rx:
            return set()
        return {self._canon[m.group(1).lower()] for m in self._rx.finditer(text)}
