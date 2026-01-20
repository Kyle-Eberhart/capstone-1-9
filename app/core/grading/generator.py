"""Question generation logic."""
from app.core.llm.client import LLMClient
from app.core.llm.prompts import load_prompt, format_prompt
from app.core.llm.guardrails import validate_response
from app.core.schemas.llm_contracts import GeneratedQuestion, GeneratedExam, GeneratedQuestionWithNumber
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
                               question_number: int | None = None) -> GeneratedQuestion:
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
        """Normalize text for comparison by removing extra whitespace and lowercasing."""
        return " ".join(text.lower().split())
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two normalized question texts using word overlap."""
        words1 = set(text1.split())
        words2 = set(text2.split())
        
        if not words1 or not words2:
            return 0.0
        
        # Calculate Jaccard similarity (intersection over union)
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        
        if union == 0:
            return 0.0
        
        similarity = intersection / union
        
        # Also check for significant word overlap (if >50% of words overlap, consider similar)
        min_len = min(len(words1), len(words2))
        if min_len > 0:
            overlap_ratio = intersection / min_len
            # Use the higher of the two similarity measures
            similarity = max(similarity, overlap_ratio * 0.8)  # Weighted overlap
        
        return similarity

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
    
    async def generate_exam(self, topic: str, num_questions: int, additional_details: str = "") -> GeneratedExam:
        """Generate multiple exam questions at once using the LLM."""
        logger.info(f"Generating exam with {num_questions} questions on topic: {topic}")
        
        # Load exam generation template
        try:
            exam_template = load_prompt("exam_gen_v1.txt")
        except FileNotFoundError:
            logger.warning("Exam generation prompt not found, using default")
            exam_template = self._get_default_exam_template()
        
        # Format the prompt - handle additional_details conditionally
        if additional_details:
            additional_details_section = f"Additional Details:\n{additional_details}"
            guidance_section = """Use the additional details provided above to tailor the questions. Consider:
- Any specific sub-topics mentioned
- Grading criteria and expectations
- Specific questions or concepts the instructor wants included
- Expected answer elements
- Any other guidance provided"""
        else:
            additional_details_section = ""
            guidance_section = "Since no additional details were provided, create well-rounded questions that cover the topic comprehensively. Make reasonable assumptions about appropriate difficulty level and scope."
        
        prompt = format_prompt(
            exam_template,
            topic=topic,
            num_questions=num_questions,
            additional_details_section=additional_details_section,
            guidance_section=guidance_section
        )
        
        system_prompt = f"""You are an expert computer science professor creating a comprehensive oral exam.

Topic: {topic}
Number of Questions: {num_questions}
{f'Additional Details: {additional_details}' if additional_details else ''}

Rules:
- Generate exactly {num_questions} unique questions
- Each question must test DIFFERENT and DISTINCT aspects of the topic
- NO two questions should cover the same concept or ask about the same thing
- Questions should vary significantly in focus, approach, and subject matter
- Questions should be appropriate for oral examination (encourage discussion)
- Provide detailed rubrics for each question
- Respond with VALID JSON ONLY
- Do NOT include explanations or extra text outside the JSON object

CRITICAL: Before finalizing your response, review all questions to ensure:
- No two questions ask about the same concept
- No two questions are rewordings of each other
- Each question tests a genuinely different aspect of the topic
- Questions cover diverse sub-topics and perspectives

Required JSON format:
{{
  "questions": [
    {{
      "question_number": 1,
      "question_text": "string",
      "context": "string",
      "rubric": "string"
    }},
    // ... more questions
  ]
}}
"""
        
        max_attempts = 5  # Increased attempts to handle duplicate detection
        for attempt in range(max_attempts):
            try:
                logger.info(f"Generating exam, attempt {attempt+1}")
                response_dict = await self.llm_client.generate_json(prompt, system_prompt)
                exam = validate_response(response_dict, GeneratedExam)
                
                if not exam:
                    logger.warning(f"Invalid exam response on attempt {attempt+1}")
                    continue
                
                # Validate we got the right number of questions
                if len(exam.questions) != num_questions:
                    logger.warning(f"Expected {num_questions} questions, got {len(exam.questions)}, retrying")
                    continue
                
                # Validate question numbers are sequential
                question_numbers = [q.question_number for q in exam.questions]
                expected_numbers = list(range(1, num_questions + 1))
                if sorted(question_numbers) != expected_numbers:
                    logger.warning(f"Question numbers are not sequential, retrying")
                    continue
                
                # Check for duplicate or very similar questions
                normalized_questions = []
                duplicates_found = False
                duplicate_pairs = []
                
                for i, q in enumerate(exam.questions):
                    normalized = self._normalize(q.question_text)
                    
                    # Check for exact duplicates
                    if normalized in normalized_questions:
                        duplicate_idx = normalized_questions.index(normalized)
                        duplicate_pairs.append((duplicate_idx + 1, i + 1))
                        logger.warning(f"Exact duplicate detected: Question {i+1} duplicates Question {duplicate_idx+1}")
                        duplicates_found = True
                    
                    # Check for high similarity (questions that are too similar)
                    for j, existing_norm in enumerate(normalized_questions):
                        similarity = self._calculate_similarity(normalized, existing_norm)
                        if similarity > 0.7:  # 70% similarity threshold
                            duplicate_pairs.append((j + 1, i + 1))
                            logger.warning(f"Highly similar questions detected: Question {i+1} is {similarity:.0%} similar to Question {j+1}")
                            duplicates_found = True
                    
                    normalized_questions.append(normalized)
                
                if duplicates_found:
                    logger.warning(f"Duplicate/similar questions found on attempt {attempt+1}: {duplicate_pairs}, retrying")
                    continue
                
                logger.info(f"Successfully generated exam with {len(exam.questions)} unique questions")
                return exam
                
            except Exception as e:
                logger.warning(f"Error generating exam on attempt {attempt+1}: {e}")
                if attempt == max_attempts - 1:
                    # Last attempt failed, use fallback
                    logger.error("All attempts failed, using fallback exam")
                    return self._get_fallback_exam(topic, num_questions)
                continue
        
        # Should not reach here, but return fallback just in case
        return self._get_fallback_exam(topic, num_questions)
    
    def _get_default_exam_template(self) -> str:
        """Default exam generation template if file not found."""
        return """Generate {num_questions} exam questions for topic: {topic}

{% if additional_details %}
Additional details: {additional_details}
{% endif %}

Respond in JSON format with a "questions" array containing {num_questions} question objects.
Each question should have: question_number, question_text, context, and rubric."""
    
    def _get_fallback_exam(self, topic: str, num_questions: int) -> GeneratedExam:
        """Get a fallback exam if LLM generation fails."""
        logger.warning(f"Using fallback exam for topic: {topic}, num_questions: {num_questions}")
        
        fallback_questions = [
            {
                "question_number": 1,
                "question_text": f"Explain the fundamental concepts related to {topic}. Provide examples and discuss their importance.",
                "context": f"This question tests understanding of core concepts in {topic}.",
                "rubric": "Grading: Understanding of concepts (40 points), Examples (30 points), Discussion of importance (30 points)."
            },
            {
                "question_number": 2,
                "question_text": f"Compare and contrast different approaches or methods within {topic}. When would you use each?",
                "context": f"This question evaluates the ability to analyze different approaches in {topic}.",
                "rubric": "Grading: Comparison (40 points), Contrast (30 points), Use cases (30 points)."
            },
            {
                "question_number": 3,
                "question_text": f"Describe a real-world application of {topic}. Explain how it works and why it's effective.",
                "context": f"This question tests practical understanding of {topic}.",
                "rubric": "Grading: Application description (40 points), Explanation (30 points), Effectiveness (30 points)."
            }
        ]
        
        # Use available fallback questions, repeat if needed
        questions = []
        for i in range(num_questions):
            fallback_idx = i % len(fallback_questions)
            question_data = fallback_questions[fallback_idx].copy()
            question_data["question_number"] = i + 1
            questions.append(GeneratedQuestionWithNumber(**question_data))
        
        return GeneratedExam(questions=questions)