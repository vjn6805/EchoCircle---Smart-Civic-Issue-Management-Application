import bcrypt
pwd = bcrypt.hashpw("tech123".encode('utf-8'), bcrypt.gensalt())
print(pwd.decode())


#techician test123
#admin admin123
#user Veer@jain123