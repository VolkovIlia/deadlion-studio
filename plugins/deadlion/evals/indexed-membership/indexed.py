n=int(input())
xs=set(range(n))
print(sum(x in xs for x in range(n)))
