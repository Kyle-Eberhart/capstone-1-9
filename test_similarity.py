"""Test similarity calculation between questions."""
from app.core.grading.generator import QuestionGenerator

generator = QuestionGenerator()

# Test cases from the actual output
q1 = "What is a hash table?"
q2 = "How does a hash table work?"
q3 = "What is a data structure?"
q4 = "What are the different types of data structures?"

print("Similarity Test Results:")
print("=" * 60)

# Normalize and calculate similarity
norm1 = generator._normalize(q1)
norm2 = generator._normalize(q2)
norm3 = generator._normalize(q3)
norm4 = generator._normalize(q4)

similarity_1_2 = generator._calculate_similarity(norm1, norm2)
similarity_1_3 = generator._calculate_similarity(norm1, norm3)
similarity_1_4 = generator._calculate_similarity(norm1, norm4)
similarity_2_3 = generator._calculate_similarity(norm2, norm3)
similarity_2_4 = generator._calculate_similarity(norm2, norm4)
similarity_3_4 = generator._calculate_similarity(norm3, norm4)

print(f"Q1: '{q1}'")
print(f"Q2: '{q2}'")
print(f"Similarity Q1-Q2: {similarity_1_2:.2%}")
print(f"Threshold: 85%")
print(f"Would be flagged: {similarity_1_2 > 0.85}")
print()

print(f"Q1: '{q1}'")
print(f"Q3: '{q3}'")
print(f"Similarity Q1-Q3: {similarity_1_3:.2%}")
print()

print(f"Q3: '{q3}'")
print(f"Q4: '{q4}'")
print(f"Similarity Q3-Q4: {similarity_3_4:.2%}")
print(f"Would be flagged: {similarity_3_4 > 0.85}")
