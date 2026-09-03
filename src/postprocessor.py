"""
PostProcessor - V4.2 T2P Production Hardened Version (LaTeX Rendering Enhanced)
Main Updates:
1. [Fix Delimiters] Unified regex replacement to eliminate delimiter residue caused by multiple escapes.
2. [Remove Over-protection] Cleaned backslash stacking in clean_json_text to avoid `\begin` becoming `\\begin`.
3. [Enhanced Cleaning] Additional processing for LaTeX line breaks and removal of meaningless spaces.
4. [Maintain Compatibility] Retained semantic deduplication and JSON parsing fault tolerance.
"""
import json
import re
import logging
import os
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

class PostProcessor:
    """Post-processor - Responsible for transforming raw LLM output into structured pedagogical data (Supports GPU acceleration)"""

    def __init__(self, similarity_threshold: float = 0.85):
        self.similarity_threshold = similarity_threshold
        self.similarity_model = None
        self._similarity_initialized = False

    def _get_similarity_model(self):
        """Load the optional embedding model only when deduplication needs it."""
        if self._similarity_initialized:
            return self.similarity_model

        self._similarity_initialized = True
        if os.getenv("ENABLE_SEMANTIC_DEDUP", "true").lower() not in ("true", "1", "yes"):
            logger.info("Semantic deduplication disabled; using text fingerprints")
            return None

        try:
            import torch
            from sentence_transformers import SentenceTransformer

            device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info("Loading semantic deduplication model on %s", device)
            self.similarity_model = SentenceTransformer(
                "paraphrase-multilingual-MiniLM-L12-v2",
                device=device,
            )
            logger.info("Semantic deduplication engine ready")
        except Exception as exc:
            logger.info("Semantic model unavailable; using text fingerprints (%s)", exc)
            self.similarity_model = None
        return self.similarity_model

    def _sanitize_text(self, text: str) -> str:
        """
        Deep clean business text: Resolve rendering anomalies and LaTeX syntax conflicts
        """
        if not isinstance(text, str) or not text:
            return text

        # 1. [Core Fix] Unify mathematical formula delimiters, use regex to avoid missing multiple escapes
        #    First process \(...\) and \[...\], then process residuals like \\$ caused by JSON escaping
        text = re.sub(r'\\\(', '$', text)          # \( → $
        text = re.sub(r'\\\)', '$', text)          # \) → $
        text = re.sub(r'\\\[', '$$', text)         # \[ → $$
        text = re.sub(r'\\\]', '$$', text)         # \] → $$

        # 2. [Fix Residual Escapes] Clear abnormal symbols like \\$, \\[, \\] caused by multiple escaping
        text = re.sub(r'\\\\\$', '$', text)        # \\$ → $
        text = re.sub(r'\\\\\[', '$$', text)       # \\[ → $$
        text = re.sub(r'\\\\\]', '$$', text)       # \\] → $$

        # 3. [LaTeX Environment Fix] Remove extra spaces or backslashes before \begin{cases}, \end{cases}, etc.
        text = re.sub(r'\\\s+begin\{', r'\\begin{', text)
        text = re.sub(r'\\\s+end\{', r'\\end{', text)

        # 4. [KaTeX Adaptation] Remove $ symbols inside cases environment (not needed inside math environment)
        if "\\begin{cases}" in text:
            def strip_dollars_in_cases(match):
                return match.group(0).replace('$', '')
            text = re.sub(r'\\begin\{cases\}.*?\\end\{cases\}', strip_dollars_in_cases, text, flags=re.DOTALL)

        # 5. [Anti-repetition] Resolve common LLM formula repetition hallucination
        text = re.sub(r'(\$?[\w\(\)\+\-\=\, ]{3,}\$?)\s+\1', r'\1', text)

        # 6. [Rendering Cleanup] Remove redundant typesetting macros
        text = re.sub(r'\\+\[\s*\d+[a-zA-Z]+\s*\]', ' ', text)
        text = re.sub(r'\\+(quad|qquad|enspace|thickspace|vspace\{.*?\}|hspace\{.*?\})', ' ', text)

        # 7. [Adhesion Fix] Ensure space between formulas and Chinese characters
        text = re.sub(r'([\u4e00-\u9fa5])\$', r'\1 $', text)
        text = re.sub(r'\$([\u4e00-\u9fa5])', r'$ \1', text)

        # 8. [Final Trim] Compress consecutive spaces, remove leading/trailing whitespace
        text = re.sub(r' +', ' ', text)
        return text.strip()

    def _recursive_sanitize(self, obj: Any) -> Any:
        """Recursively traverse JSON structure and clean all string fields"""
        if isinstance(obj, str):
            return self._sanitize_text(obj)
        elif isinstance(obj, list):
            return [self._recursive_sanitize(item) for item in obj]
        elif isinstance(obj, dict):
            return {k: self._recursive_sanitize(v) for k, v in obj.items()}
        return obj

    def clean_json_text(self, text: str) -> str:
        """Protection logic for LaTeX backslashes in JSON parsing (avoid extra escaping)"""
        if not text:
            return ""

        # Remove Markdown code block markers
        text = re.sub(r'^```json\s*|\s*```$', '', text.strip(), flags=re.MULTILINE)

        # Locate valid JSON boundaries
        start_idx = text.find('{')
        end_idx = text.rfind('}')
        if start_idx == -1 or end_idx == -1:
            return text
        text = text[start_idx:end_idx + 1]

        # [Key Modification] Only protect double backslashes (LaTeX line breaks), no longer add backslash to all LaTeX commands
        # Original logic would cause \begin → \\begin, ultimately displaying as \begin or even \\begin in the frontend
        text = text.replace('\\\\', '___DBL___')   # Protect existing double backslashes
        # Removed original re.sub(r'\\([a-zA-Z]+)', ...) line, no longer add extra escaping to commands
        text = text.replace('___DBL___', '\\\\')   # Restore double backslashes

        # Filter invisible control characters
        text = "".join(ch for ch in text if ord(ch) >= 32 or ch in "\n\r\t")
        return text

    def parse_json(self, text: str) -> Optional[Dict]:
        """Enhanced parser: Handle JSON syntax errors and escape conflicts"""
        cleaned = self.clean_json_text(text)
        try:
            # Attempt standard parsing
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.debug(f"Standard parsing failed, attempting fault-tolerant repair: {e}")
            try:
                # Fix trailing commas and irregular line breaks
                fixed = re.sub(r',\s*([\]}])', r'\1', cleaned)
                fixed = fixed.replace('\n', '\\n').replace('\r', '')
                return json.loads(fixed)
            except Exception as final_e:
                logger.error(f"JSON parsing failed completely: {str(final_e)}")
                return None

    def _normalize_problem(self, problem: Dict) -> Dict:
        """Ensure field alignment, fill in missing dimensions"""
        if not isinstance(problem, dict):
            return problem

        # 1. Problem statement mapping
        if 'statement' in problem and 'problem_statement' not in problem:
            problem['problem_statement'] = problem.pop('statement')

        # 2. Answer mapping
        answer_variants = ['correct_answer', 'target_answer', 'ans', 'res']
        for var in answer_variants:
            if var in problem and 'answer' not in problem:
                problem['answer'] = problem.pop(var)

        # 3. Scaffolding and solution completion
        if 'analysis' in problem and 'scaffolding' not in problem:
            problem['scaffolding'] = problem.get('analysis')

        if 'solution' not in problem:
            if 'answer' in problem:
                problem['solution'] = f"Standard solution: {problem['answer']}"
            elif 'correct_values' in problem:
                vals = ", ".join(map(str, problem['correct_values']))
                problem['solution'] = f"Standard values: {vals}"

        # Force ensure problem_statement exists
        if 'problem_statement' not in problem:
            problem['problem_statement'] = "Problem parsing exception, please regenerate."

        return problem

    def process(self, raw_text: str, topic: str = None) -> Optional[Dict]:
        """Main entry: Execute parse -> clean -> align -> validate pipeline"""
        data = self.parse_json(raw_text)
        if not data:
            return None

        # 1. Recursively clean text (resolve repetition and rendering conflicts)
        data = self._recursive_sanitize(data)

        # 2. Pattern recognition processing
        exam_keys = ['section_a_mcq', 'section_b_fill_in', 'section_c_long_questions']
        if any(key in data for key in exam_keys):
            return data

        # 3. Field standardization
        problem = self._normalize_problem(data)

        # 4. Difficulty and metadata correction
        try:
            d = int(problem.get('difficulty', 3))
            problem['difficulty'] = max(1, min(5, d))
        except Exception:
            problem['difficulty'] = 3

        if topic:
            problem['topic'] = topic

        return problem

    def deduplicate(self, problems: List[Dict], existing: List[Dict] = None) -> List[Dict]:
        """Transformer-based semantic deduplication (supports fallback when model is unavailable)"""
        if not problems:
            return []

        similarity_model = self._get_similarity_model()
        if similarity_model is None:
            return self._basic_deduplicate(problems, existing)

        import torch
        from sentence_transformers import util

        new_texts = [p.get('problem_statement', '') for p in problems
                     if isinstance(p, dict) and p.get('problem_statement')]
        if not new_texts:
            return problems

        new_embeddings = similarity_model.encode(new_texts, convert_to_tensor=True)

        pool_embeddings = None
        if existing:
            existing_texts = [p.get('problem_statement', '') for p in existing
                              if isinstance(p, dict) and p.get('problem_statement')]
            if existing_texts:
                pool_embeddings = similarity_model.encode(existing_texts, convert_to_tensor=True)

        unique_problems = []
        for i, emb in enumerate(new_embeddings):
            is_duplicate = False
            if pool_embeddings is not None:
                sims = util.cos_sim(emb, pool_embeddings)[0]
                max_sim = torch.max(sims).item()
                if max_sim > self.similarity_threshold:
                    is_duplicate = True

            if not is_duplicate:
                unique_problems.append(problems[i])
                emb_unsqueezed = emb.unsqueeze(0)
                if pool_embeddings is not None:
                    pool_embeddings = torch.cat([pool_embeddings, emb_unsqueezed])
                else:
                    pool_embeddings = emb_unsqueezed

        return unique_problems

    def _basic_deduplicate(self, problems: List[Dict], existing: List[Dict] = None) -> List[Dict]:
        """Text fingerprinting deduplication fallback scheme"""
        seen = set()
        if existing:
            for p in existing:
                if not isinstance(p, dict):
                    continue
                fp = re.sub(r'\s+', '', str(p.get('problem_statement', '')))
                seen.add(fp)

        unique = []
        for p in problems:
            if not isinstance(p, dict):
                unique.append(p)
                continue
            fp = re.sub(r'\s+', '', str(p.get('problem_statement', '')))
            if fp not in seen:
                unique.append(p)
                seen.add(fp)
        return unique
