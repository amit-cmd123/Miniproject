# Answer Key and Marking Scheme — EVN-PROG-01

**Total: 30 marks · six questions · 5 marks each**

Each criterion lists the **essential concepts** a correct answer must contain and the
**acceptable alternatives** that also earn the mark. The alternatives exist because
students phrase things differently *and* because transcription is imperfect — a
criterion must survive a few wrong characters.

Criterion marks for every question sum to exactly 5. A validator enforces this.

---

## Q1 — while vs do-while (5 marks)

**Model answer**

> A while loop is entry controlled. The condition is checked before the body is
> executed, so if the condition is false at the start the body never runs.
> A do-while loop is exit controlled. The body is executed first and the condition
> is checked afterwards, so the body always runs at least once.
>
> Syntax:
> while (condition) { statements }
> do { statements } while (condition);
>
> do-while is better when the statements must run at least once, for example
> showing a menu to the user before asking whether they want to continue.

| # | Criterion | Marks | Essential concepts | Acceptable alternatives |
|---|---|---|---|---|
| 1 | while checks the condition **before** the body | 1.5 | condition checked first; entry controlled | "pre-test loop", "tests at the top", "may run zero times" |
| 2 | do-while checks the condition **after** the body | 1.5 | condition checked after; exit controlled | "post-test loop", "tests at the bottom" |
| 3 | do-while body runs **at least once** | 1 | executes minimum one time | "runs once even if condition is false", "guaranteed one iteration" |
| 4 | Correct syntax **or** a valid use case | 1 | while(cond){} / do{}while(cond); | a menu example, a retry-until-valid-input example |

**Common mistakes:** saying while runs at least once (reversed); omitting the
semicolon after the closing while of a do-while — *not penalised, syntax detail only*.

---

## Q2 — Output prediction (5 marks)

**Correct output: 9**

**Model answer**

> The output is 9. The loop runs from 1 to 5. When i is even the continue statement
> skips the addition, so only the odd numbers 1, 3 and 5 are added. 1 + 3 + 5 = 9.

| # | Criterion | Marks | Essential concepts | Acceptable alternatives |
|---|---|---|---|---|
| 1 | States the output is **9** | 2 | 9 | "sum = 9", "output: 9" |
| 2 | Explains that continue skips the even values | 2 | continue skips even iterations | "skips when i%2==0", "even numbers are not added" |
| 3 | Shows the odd numbers added: 1 + 3 + 5 | 1 | 1+3+5 | "only the odd numbers are summed" |

**Common mistakes:** answering 15 (ignoring continue); answering 6 (summing the evens).

**Load-bearing token:** the digit **9**. If the line carrying it is low confidence,
route the answer to a human rather than marking it.

---

## Q3 — Find the three errors (5 marks)

**The three errors**

1. `int n = 5` — missing semicolon → `int n = 5;`
2. `if (n = 10)` — assignment used instead of comparison → `if (n == 10)`
3. `for (i = 0; ...)` — `i` is never declared → add `int i;` or write `for (int i = 0; ...)`

| # | Criterion | Marks | Essential concepts | Acceptable alternatives |
|---|---|---|---|---|
| 1 | Missing semicolon after int n = 5, identified and corrected | 1.5 | missing semicolon | "no ; at end of line", "statement not terminated" |
| 2 | = vs == in the if condition, identified and corrected | 2 | assignment instead of comparison | "should be ==", "= assigns, == compares" |
| 3 | Undeclared variable i, identified and corrected | 1.5 | i not declared | "declare int i", "i is undefined" |

**Note for the marker:** the `==` error carries the most marks because it is the only
one that changes program behaviour rather than merely failing to compile.

**Common mistakes:** listing indentation or a missing newline in printf as an error — neither is an error.

**Load-bearing token:** `==` versus `=`. A single misread stroke flips this answer,
so the confidence threshold on that line decides whether it is auto-marked.

---

## Q4 — Prime number program (5 marks)

**Model answer**

```c
#include <stdio.h>
int main()
{
    int n, i, flag = 0;
    scanf("%d", &n);
    for (i = 2; i < n; i++) {
        if (n % i == 0) {
            flag = 1;
            break;
        }
    }
    if (flag == 0)
        printf("Prime");
    else
        printf("Not Prime");
    return 0;
}
```

| # | Criterion | Marks | Essential concepts | Acceptable alternatives |
|---|---|---|---|---|
| 1 | Declares the variables and obtains n | 1 | int n declared; input taken or n supplied | n passed as a parameter; n hard-coded |
| 2 | A loop that tests divisors of n | 2 | for or while loop starting at 2 | i <= n/2, i*i <= n, sqrt(n) — all correct, and better |
| 3 | Divisibility tested with the modulus operator | 1 | n % i == 0 | "if the remainder is zero", !(n%i) |
| 4 | Prints Prime / Not Prime on the correct branch | 1 | correct branch reached | flag variable or early return; any equivalent wording |

**Common mistakes:** starting the loop at i = 1 (everything is divisible by 1, so the
answer is always "Not Prime"); looping to i <= n (n divides itself).
*Handling n ≤ 1 is not required for full marks.*

---

## Q5 — Pointers (5 marks)

**Model answer**

> A pointer is a variable that stores the memory address of another variable.
> The & operator is the address-of operator; it gives the memory address of a variable.
> The * operator is the dereference operator; it gives the value stored at an address.
>
> int x = 10;
> int *p = &x;
> printf("%d", *p);

| # | Criterion | Marks | Essential concepts | Acceptable alternatives |
|---|---|---|---|---|
| 1 | A pointer stores the **address** of another variable | 2 | variable holding an address | "holds the memory location of another variable", "points to a variable" |
| 2 | & is the address-of operator | 1 | gives the address | "returns the location of the variable", "reference operator" |
| 3 | * dereferences — gives the value at the address | 1 | value at that address | "the value stored there", "indirection operator", "contents of" |
| 4 | A valid three-line example using a pointer | 1 | declaration, address assignment, use | any correct snippet; printf not required |

**Common mistakes:** swapping the meanings of & and *; saying a pointer "stores a value".

---

## Q6 — Largest element in an array (5 marks)

**Model answer**

```c
int largest(int arr[], int n)
{
    int i, max;
    max = arr[0];
    for (i = 1; i < n; i++) {
        if (arr[i] > max)
            max = arr[i];
    }
    return max;
}
```

| # | Criterion | Marks | Essential concepts | Acceptable alternatives |
|---|---|---|---|---|
| 1 | Correct function signature: array and size as parameters | 1 | (int arr[], int n) | int *arr; a void function that prints; different parameter names |
| 2 | max initialised with the first element | 1 | max = arr[0] | initialising with a very small value such as INT_MIN |
| 3 | Loop traversing the array with a comparison | 2 | loop over the elements; if (arr[i] > max) | while loop; starting at i = 0 |
| 4 | Returns or prints the largest value | 1 | returns max | prints the value instead of returning it |

**Common mistakes:** initialising max = 0, which fails for an all-negative array —
**deduct criterion 2 only**; looping to i <= n, which reads past the end — not
penalised unless the logic breaks.

---

## How transcription errors are treated

These four rules stop a reading error from becoming a marking error. They are the
reason this paper can be marked reliably even at 85–90% character accuracy.

1. **Spelling is never marked.** "poiner", "varaible", "retrun" earn full marks.
2. **A criterion matches on concept, not on exact words.** Every alternative listed
   above is worth the same as the model wording.
3. **Load-bearing tokens are the exception**: `==` versus `=`, a variable name, and a
   numeric answer such as the `9` in Q2. When the line carrying one of these falls
   below the confidence threshold, the answer is routed to a human instead of being
   marked automatically.
4. **An unreadable answer is never guessed.** It goes to the examiner with the
   original handwriting beside it.
