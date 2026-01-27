"""Question generation logic."""
import json
import logging
from typing import Optional
from app.core.llm.client import LLMClient
from app.core.llm.prompts import load_prompt, format_prompt
from app.core.llm.guardrails import validate_response
from app.core.schemas.llm_contracts import GeneratedQuestion, GeneratedExam, GeneratedQuestionWithNumber

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

        # Check if API key is available before attempting LLM generation
        try:
            # Try to get the client to check if API key is set
            _ = self.llm_client._get_api_key()
            api_key_available = bool(_)
        except Exception:
            api_key_available = False
        
        if not api_key_available:
            logger.info(f"API key not available, using fallback question for question #{question_number}")
            fallback = self._get_fallback_question(question_number)
            normalized = self._normalize(fallback.question_text)
            self.generated_questions.add(normalized)
            return fallback
        
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
                
            except RuntimeError as e:
                # Check if it's an API key error
                if "TOGETHER_API_KEY" in str(e) or "API key" in str(e).lower():
                    logger.info(f"API key not available, using fallback question for question #{question_number}")
                    fallback = self._get_fallback_question(question_number)
                    normalized = self._normalize(fallback.question_text)
                    self.generated_questions.add(normalized)
                    return fallback
                logger.warning(f"Error generating question #{question_number}: {e}")
                continue  # Try again
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
        """Calculate similarity between two normalized question texts using multiple heuristics."""
        words1 = set(text1.split())
        words2 = set(text2.split())
        
        if not words1 or not words2:
            return 0.0
        
        # Calculate Jaccard similarity (intersection over union)
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        
        if union == 0:
            return 0.0
        
        jaccard = intersection / union
        
        # Also check for significant word overlap (if >50% of words overlap, consider similar)
        min_len = min(len(words1), len(words2))
        overlap_ratio = intersection / min_len if min_len > 0 else 0.0
        
        # Extract key terms (words longer than 3 chars, excluding common question words)
        common_words = {'what', 'how', 'why', 'when', 'where', 'does', 'is', 'are', 'the', 'a', 'an', 'and', 'or', 'but', 'do', 'can', 'will'}
        key_terms1 = {w for w in words1 if len(w) > 3 and w not in common_words}
        key_terms2 = {w for w in words2 if len(w) > 3 and w not in common_words}
        
        # If they share significant key terms (the actual subject matter), boost similarity
        key_similarity = 0.0
        if key_terms1 and key_terms2:
            key_intersection = len(key_terms1 & key_terms2)
            key_union = len(key_terms1 | key_terms2)
            key_similarity = key_intersection / key_union if key_union > 0 else 0.0
        
        # Combine metrics: if key terms are very similar, questions are likely about the same thing
        # even if the phrasing differs (e.g., "What is X?" vs "How does X work?")
        if key_similarity > 0.6:  # More than 60% of key terms match
            # Boost similarity significantly - these are likely about the same concept
            similarity = max(jaccard, overlap_ratio * 0.8, key_similarity * 0.9)
        else:
            similarity = max(jaccard, overlap_ratio * 0.8)
        
        # Additional check: if questions are short and share most key terms, they're similar
        if min_len <= 6 and key_similarity > 0.5:
            similarity = max(similarity, 0.75)
        
        return min(similarity, 1.0)  # Cap at 1.0

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
        
        # Check if API key is available before attempting LLM generation
        try:
            api_key = self.llm_client._get_api_key()
            api_key_available = bool(api_key)
        except Exception:
            api_key_available = False
        
        if not api_key_available:
            logger.info(f"API key not available, using fallback questions for exam with {num_questions} questions")
            # Generate fallback questions
            fallback_questions = []
            for i in range(1, num_questions + 1):
                fallback_q = self._get_fallback_question(i)
                fallback_questions.append(GeneratedQuestionWithNumber(
                    question_number=i,
                    question_text=fallback_q.question_text,
                    context=fallback_q.context,
                    rubric=fallback_q.rubric
                ))
            return GeneratedExam(questions=fallback_questions)
        
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

IMPORTANT: Respond ONLY in English. Do NOT include any explanatory text before or after the JSON. Respond with ONLY the JSON object, nothing else.

Topic: {topic}
Number of Questions: {num_questions}
{f'Additional Details: {additional_details}' if additional_details else ''}

CRITICAL REQUIREMENTS:

1. UNIQUENESS - Each question MUST be completely different:
   - NO repeating the same concept in different words
   - NO asking about the same data structure/concept multiple times
   - Each question explores a DIFFERENT facet of the topic
   - Cover diverse sub-topics, perspectives, and approaches
   - Example: If topic is "Data Structures", don't ask about hash tables twice
   - Instead: Ask about hash tables, then arrays, then trees, then graphs, etc.

2. RUBRIC FORMAT - MUST be a STRING, not a dictionary:
   ✅ CORRECT: "rubric": "Grading: Understanding (25 points), Application (25 points), Examples (25 points), Analysis (25 points). Total: 100 points."
   ❌ WRONG: "rubric": {{"Understanding": 25, "Application": 25}}
   
3. JSON FORMAT:
   - Generate exactly {num_questions} questions
   - Number sequentially from 1 to {num_questions}
   - All fields must be strings (question_text, context, rubric)
   - Valid JSON only, no markdown code blocks

BEFORE FINALIZING:
- Review all questions to ensure uniqueness
- Verify all rubrics are strings
- Check question numbers are sequential
- Ensure JSON is valid

Required JSON format:
{{
  "questions": [
    {{
      "question_number": 1,
      "question_text": "string",
      "context": "string",
      "rubric": "string (NOT a dictionary)"
    }},
    // ... more questions
  ]
}}
"""
        
        max_attempts = 5  # Increased attempts to handle duplicate detection
        failure_reasons = []  # Track all failure reasons across attempts
        
        for attempt in range(max_attempts):
            try:
                logger.info(f"Generating exam, attempt {attempt+1}/{max_attempts}")
                logger.debug(f"Topic: {topic}, Num questions: {num_questions}, Additional details length: {len(additional_details)} chars")
                
                response_dict = await self.llm_client.generate_json(prompt, system_prompt)
                logger.debug(f"Received response dict with keys: {list(response_dict.keys())}")
                
                # Fix rubric format if LLM returned dictionaries instead of strings
                if "questions" in response_dict:
                    logger.debug(f"Response contains 'questions' key with {len(response_dict['questions'])} items")
                    for q in response_dict["questions"]:
                        if "rubric" in q and isinstance(q["rubric"], dict):
                            # Convert dictionary rubric to string
                            rubric_dict = q["rubric"]
                            rubric_parts = []
                            for key, value in rubric_dict.items():
                                rubric_parts.append(f"{key}: {value} points")
                            q["rubric"] = "Grading criteria: " + ", ".join(rubric_parts) + ". Total: " + str(sum(rubric_dict.values())) + " points."
                            logger.info(f"Converted rubric dictionary to string for question {q.get('question_number', '?')}")
                else:
                    error_msg = f"Response dict missing 'questions' key. Keys present: {list(response_dict.keys())}"
                    logger.error(error_msg)
                    failure_reasons.append(f"Attempt {attempt+1}: {error_msg}")
                    continue
                
                exam = validate_response(response_dict, GeneratedExam)
                
                if not exam:
                    error_msg = f"Invalid exam response - validation failed"
                    logger.error(f"{error_msg} on attempt {attempt+1}")
                    logger.error(f"Response dict structure: {response_dict}")
                    failure_reasons.append(f"Attempt {attempt+1}: {error_msg}")
                    continue
                
                # Validate we got the right number of questions
                if len(exam.questions) != num_questions:
                    error_msg = f"Expected {num_questions} questions, got {len(exam.questions)}"
                    logger.warning(f"{error_msg}, retrying")
                    failure_reasons.append(f"Attempt {attempt+1}: {error_msg}")
                    continue
                
                # Validate question numbers are sequential
                question_numbers = [q.question_number for q in exam.questions]
                expected_numbers = list(range(1, num_questions + 1))
                if sorted(question_numbers) != expected_numbers:
                    error_msg = f"Question numbers not sequential. Got: {question_numbers}, Expected: {expected_numbers}"
                    logger.warning(f"{error_msg}, retrying")
                    failure_reasons.append(f"Attempt {attempt+1}: {error_msg}")
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
                        if similarity > 0.85:  # 85% similarity threshold (raised from 70% to be less strict)
                            duplicate_pairs.append((j + 1, i + 1))
                            logger.warning(f"Highly similar questions detected: Question {i+1} is {similarity:.0%} similar to Question {j+1}")
                            duplicates_found = True
                    
                    normalized_questions.append(normalized)
                
                if duplicates_found:
                    error_msg = f"Duplicate/similar questions found: {duplicate_pairs}"
                    logger.warning(f"{error_msg}, retrying")
                    failure_reasons.append(f"Attempt {attempt+1}: {error_msg}")
                    continue
                
                logger.info(f"Successfully generated exam with {len(exam.questions)} unique questions")
                return exam
                
            except RuntimeError as e:
                # Check if it's an API key error
                if "TOGETHER_API_KEY" in str(e) or "API key" in str(e).lower() or "not set" in str(e).lower():
                    logger.info(f"API key not available, using fallback questions for exam with {num_questions} questions")
                    # Generate fallback questions
                    fallback_questions = []
                    for i in range(1, num_questions + 1):
                        fallback_q = self._get_fallback_question(i)
                        fallback_questions.append(GeneratedQuestionWithNumber(
                            question_number=i,
                            question_text=fallback_q.question_text,
                            context=fallback_q.context,
                            rubric=fallback_q.rubric
                        ))
                    return GeneratedExam(questions=fallback_questions)
                
                # LLM API call failed for other reasons
                error_msg = f"LLM API call failed: {str(e)}"
                logger.error(f"{error_msg} on attempt {attempt+1}")
                failure_reasons.append(f"Attempt {attempt+1}: {error_msg}")
                if attempt == max_attempts - 1:
                    # Last attempt failed - use fallback questions instead of raising error
                    logger.warning(f"LLM API call failed after {max_attempts} attempts. Using fallback questions.")
                    all_failures = "\n".join(failure_reasons)
                    logger.error(f"All failures:\n{all_failures}")
                    # Generate fallback questions instead of raising error
                    fallback_questions = []
                    for i in range(1, num_questions + 1):
                        fallback_q = self._get_fallback_question(i)
                        fallback_questions.append(GeneratedQuestionWithNumber(
                            question_number=i,
                            question_text=fallback_q.question_text,
                            context=fallback_q.context,
                            rubric=fallback_q.rubric
                        ))
                    return GeneratedExam(questions=fallback_questions)
                continue
            except json.JSONDecodeError as e:
                # JSON parsing failed
                error_msg = f"JSON parsing failed: {str(e)}"
                logger.error(f"{error_msg} on attempt {attempt+1}")
                failure_reasons.append(f"Attempt {attempt+1}: {error_msg}")
                if attempt == max_attempts - 1:
                    # Use fallback questions instead of raising error
                    logger.warning(f"JSON parsing failed after {max_attempts} attempts. Using fallback questions.")
                    all_failures = "\n".join(failure_reasons)
                    logger.error(f"All failures:\n{all_failures}")
                    fallback_questions = []
                    for i in range(1, num_questions + 1):
                        fallback_q = self._get_fallback_question(i)
                        fallback_questions.append(GeneratedQuestionWithNumber(
                            question_number=i,
                            question_text=fallback_q.question_text,
                            context=fallback_q.context,
                            rubric=fallback_q.rubric
                        ))
                    return GeneratedExam(questions=fallback_questions)
                continue
            except Exception as e:
                # Other unexpected errors
                error_type = type(e).__name__
                error_msg = f"Unexpected error ({error_type}): {str(e)}"
                logger.error(f"{error_msg} on attempt {attempt+1}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
                failure_reasons.append(f"Attempt {attempt+1}: {error_msg}")
                if attempt == max_attempts - 1:
                    # Use fallback questions instead of raising error
                    logger.warning(f"Unexpected error after {max_attempts} attempts. Using fallback questions.")
                    all_failures = "\n".join(failure_reasons)
                    logger.error(f"All failures:\n{all_failures}")
                    logger.error(f"Error type: {error_type}, Error message: {str(e)}")
                    fallback_questions = []
                    for i in range(1, num_questions + 1):
                        fallback_q = self._get_fallback_question(i)
                        fallback_questions.append(GeneratedQuestionWithNumber(
                            question_number=i,
                            question_text=fallback_q.question_text,
                            context=fallback_q.context,
                            rubric=fallback_q.rubric
                        ))
                    return GeneratedExam(questions=fallback_questions)
                continue
        
        # Should not reach here, but use fallback questions if we do
        logger.warning(f"Exam generation loop completed without success. Using fallback questions.")
        all_failures = "\n".join(failure_reasons) if failure_reasons else "Unknown error - no attempts completed"
        logger.error(f"All failures:\n{all_failures}")
        fallback_questions = []
        for i in range(1, num_questions + 1):
            fallback_q = self._get_fallback_question(i)
            fallback_questions.append(GeneratedQuestionWithNumber(
                question_number=i,
                question_text=fallback_q.question_text,
                context=fallback_q.context,
                rubric=fallback_q.rubric
            ))
        return GeneratedExam(questions=fallback_questions)
    
    def _get_default_exam_template(self) -> str:
        """Default exam generation template if file not found."""
        return """Generate {num_questions} exam questions for topic: {topic}

{% if additional_details %}
Additional details: {additional_details}
{% endif %}

Respond in JSON format with a "questions" array containing {num_questions} question objects.
Each question should have: question_number, question_text, context, and rubric."""
    