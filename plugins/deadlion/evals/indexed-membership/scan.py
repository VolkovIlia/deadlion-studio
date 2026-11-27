n=int(input())
xs=list(range(n))
print(sum(x in xs for x in range(n)))
