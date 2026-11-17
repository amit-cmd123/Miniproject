# Programming Fundamentals in C — Class Test

**Exam code:** EVN-PROG-01  ·  **Maximum marks:** 30  ·  **Time:** 45 minutes

---

### Instructions to the candidate

1. Answer **all six** questions. Each question carries **5 marks**.
2. Write the **question number** clearly at the start of every answer, like `Q1.`
3. Use a **blue or black pen only.** No pencil, no red ink, no gel pen that bleeds through.
4. Leave **one blank line** between two answers.
5. Write only inside the ruled area. Do **not** write in the margin.
6. Code may be written in C. Indentation is not marked — correctness of logic is.

---

## Q1. [5 marks]

State the difference between a `while` loop and a `do-while` loop.
Give the syntax of each, and state one situation where `do-while` is the better choice.

## Q2. [5 marks]

Write the output of the following program and explain in one or two lines why that output is produced.

```
int i, sum = 0;
for (i = 1; i <= 5; i++) {
    if (i % 2 == 0)
        continue;
    sum = sum + i;
}
printf("%d", sum);
```

## Q3. [5 marks]

The program below contains **three errors**. Identify each error and write the corrected line.

```
#include <stdio.h>
int main()
{
    int n = 5
    if (n = 10)
        printf("ten");
    for (i = 0; i < n; i++)
        printf("%d", i);
    return 0;
}
```

## Q4. [5 marks]

Write a C program to check whether a number `n` is a prime number.
Print `Prime` if it is prime and `Not Prime` otherwise.

## Q5. [5 marks]

What is a pointer?
Explain the meaning of the `&` operator and the `*` operator.
Write a short example of three lines using a pointer.

## Q6. [5 marks]

Write a C function that takes an integer array and its size, and returns the **largest element** in the array.

---

*End of paper*
