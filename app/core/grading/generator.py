"""Question generation logic."""
from typing import Optional
from app.core.llm.client import LLMClient
from app.core.llm.prompts import load_prompt, format_prompt
from app.core.llm.guardrails import validate_response
from app.core.schemas.llm_contracts import GeneratedQuestion
import logging

logger = logging.getLogger(__name__)


class QuestionGenerator:
    """Generates exam questions using LLM."""
    
    def __init__(self):
        self.llm_client = LLMClient()
        self.prompt_template = None
        self._load_template()
        self._question_counter = 0
        self.generated_questions = set()
    
    def _load_template(self):
        """Load the question generation prompt template."""
        try:
            self.prompt_template = load_prompt("question_gen_v1.txt")
        except FileNotFoundError:
            logger.warning("Question generation prompt not found, using default")
            self.prompt_template = self._get_default_template()
    
    def _get_default_template(self) -> str:
        """Default template if file not found."""
        return """Generate an essay-style exam question for a computer science course.

Topic: {topic}
Difficulty: {difficulty}
Question Number: {question_number}

Requirements:
1.Each question you generate must be unique for the exam. Do not repeat previous questions. 
2. Provide relevant background context
3. Provide a detailed grading rubric

Important: Respond only in JSON format exactly like this:
{
    "question_text": "The question text",
    "context": "Background context and information",
    "rubric": "Detailed grading rubric with criteria"
}
Do not add anything else outside the JSON object."""
    
    async def generate_question(self, topic: str = "Computer Science", difficulty: str = "Intermediate", 
                               question_number: Optional[int] = None) -> GeneratedQuestion:
        """Generate a question using the LLM."""
        if question_number is None:
            self._question_counter += 1
            question_number = self._question_counter

        max_attempts = 5  # Retry LLM generation if duplicate
        for attempt in range(max_attempts):
            logger.info(f"Generating question #{question_number}, attempt {attempt+1}")
            prompt = format_prompt(
                self.prompt_template,
                topic=topic,
                difficulty=difficulty,
                question_number=question_number
            )

            system_prompt = f"""
            You are an expert computer science professor generating exam questions.

Topic: {topic}
Difficulty: {difficulty}
Question Number: {question_number}

Rules:
- Generate a NEW and UNIQUE question for each question number.
- Do NOT repeat previous questions.
- Respond with VALID JSON ONLY.
- Do NOT include explanations or extra text.

Required JSON format:
{{
  "question_text": "string",
  "context": "string",
  "rubric": "string"
}}
"""
        
        
            try:
                response_dict = await self.llm_client.generate_json(prompt, system_prompt)
                question = validate_response(response_dict, GeneratedQuestion)
                if not question:
                    continue  # Invalid response, try again

                normalized = self._normalize(question.question_text)
                if normalized in self.generated_questions:
                    logger.warning(f"Duplicate detected for question #{question_number}, retrying LLM")
                    continue  # Try again

                # Unique question
                self.generated_questions.add(normalized)
                return question
                
            except Exception as e:
                logger.warning(f"Error generating question #{question_number}: {e}")
                continue  # Try again
        # If all attempts fail or duplicates keep appearing, use a fallback
        fallback = self._get_fallback_question(question_number)
        normalized = self._normalize(fallback.question_text)
        self.generated_questions.add(normalized)
        return fallback
        
    def _normalize(self, text: str) -> str:
        return " ".join(text.lower().split())

    def _get_fallback_question(self, question_number: int) -> GeneratedQuestion:
        """Get a fallback question based on question number."""
        fallback_questions = [
            {
                "question_text": "Explain the fundamental principles of data structures. Discuss the differences between arrays and linked lists, and when you would use each.",
                "context": "Data structures are fundamental to computer science. Arrays store elements in contiguous memory, while linked lists use nodes with pointers.",
                "rubric": "Grading criteria: (1) Understanding of arrays - 25 points, (2) Understanding of linked lists - 25 points, (3) Comparison - 25 points, (4) Use cases - 25 points."
            },
            {
                "question_text": "Describe the concept of algorithm time complexity (Big O notation). Provide examples of O(1), O(n), and O(n²) algorithms.",
                "context": "Algorithm complexity analysis helps developers understand how algorithms scale. Big O notation describes worst-case time complexity.",
                "rubric": "Grading criteria: (1) Explanation of Big O - 30 points, (2) O(1) example - 20 points, (3) O(n) example - 20 points, (4) O(n²) example - 20 points, (5) Importance - 10 points."
            },
            {
                "question_text": "Explain the concept of recursion in programming. Discuss its advantages and disadvantages, and provide an example.",
                "context": "Recursion is a programming technique where a function calls itself. It's used in tree traversal and divide-and-conquer algorithms.",
                "rubric": "Grading criteria: (1) Explanation - 25 points, (2) Advantages - 20 points, (3) Disadvantages - 20 points, (4) Example - 30 points, (5) Clarity - 5 points."
            }
        ]
        
        # Pick the first fallback not yet used
        for fallback in fallback_questions:
            normalized = self._normalize(fallback["question_text"])
            if normalized not in self.generated_questions:
                return GeneratedQuestion(
                    question_text=fallback["question_text"],
                    context=fallback["context"],
                    rubric=fallback["rubric"]
                )

        # If all fallback questions already used, generate a generic one
        generic_fallback = {
            "question_text": f"Generic CS question #{question_number}.",
            "context": "This is a fallback question.",
            "rubric": "Grading criteria: complete answer - 100 points."
        }
        return GeneratedQuestion(**generic_fallback)
