method Sum(n: int) returns (s: int)
  requires n >= 0
  ensures s == n * (n + 1) / 2
{
  s := 0;
  var i := 0;
  while i < n
    invariant 0 <= i <= n
    invariant s == i * i
  {
    i := i + 1;
    s := s + i;
  }
}
