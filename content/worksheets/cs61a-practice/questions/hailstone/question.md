id: hailstone
title: Hailstone
code: hailstone.py
---

Douglas Hofstadter's Pulitzer-prize-winning book, *Gödel, Escher, Bach*, poses
the following mathematical puzzle.

1. Pick a positive integer `n` as the start.
2. If `n` is even, divide it by 2.
3. If `n` is odd, multiply it by 3 and add 1.
4. Continue this process until `n` is 1.

The number `n` will travel up and down but eventually end at 1 (at least for
all numbers that have ever been tried—nobody has ever proved that the
sequence will terminate). Analogously, a hailstone travels up and down in the
atmosphere before eventually landing on earth.

This sequence of values of `n` is often called a Hailstone sequence. Write a
function that takes a single argument with formal parameter name `n`, prints
out the hailstone sequence starting at `n`, and returns the number of steps in
the sequence:

@code hailstone.py

Hailstone sequences can get quite long! Try 27. What's the longest you can
find?

> Note that if `n == 1` initially, then the sequence is one step long. <br>
> **Hint:** If you see 4.0 but want just 4, try using floor division `//` instead of regular division `/`.

@pytest hailstone

**Curious about hailstone sequences? Take a look at this article:**
* In 2019, there was a major [development](https://www.quantamagazine.org/mathematician-terence-tao-and-the-collatz-conjecture-20191211/) in understanding how the hailstone conjecture works for most numbers! This [2026 StarTalk interview](https://www.youtube.com/watch?v=IkPOwoqkE2Q) with Terence Tao discusses the problem.

:::solution

We keep track of the current length of the hailstone sequence and the current
value of the hailstone sequence. From there, we loop until we hit the end of
the sequence, updating the length in each step.

> Note: we need to do floor division `//` to remove decimals.

:::
