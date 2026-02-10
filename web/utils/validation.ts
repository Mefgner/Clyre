const minPasswordLength = 8

const emailRegex = /^[\w._%+-]+@[\w.-]+\.[a-zA-Z]{2,}$/

const usernameRegex = /^[\w_]+$/

const passwordStrengthRegexUppercase = /[A-Z]/
const passwordStrengthRegexLowercase = /[a-z]/
const passwordStrengthRegexNumber = /\d/
const passwordStrengthRegexSpecialChar = /\W/

export function validateRegisterCredentials (username: string, email: string, password: string, second_password: string): string | null {
  if (username.length < 31 && username.length > 3) {
    return 'Username must be between 3 and 30 characters long.'
  }

  if (!usernameRegex.test(username)) {
    return 'Username can only contain letters, numbers, and underscores.'
  }

  if (!emailRegex.test(email)) {
    return 'Invalid email format.'
  }

  if (password.length < minPasswordLength) {
    return `Password must be at least ${minPasswordLength} characters long.`
  }

  if (!passwordStrengthRegexUppercase.test(password)) {
    return 'Password must contain at least one uppercase letter.'
  }

  if (!passwordStrengthRegexLowercase.test(password)) {
    return 'Password must contain at least one lowercase letter.'
  }

  if (!passwordStrengthRegexNumber.test(password)) {
    return 'Password must contain at least one number.'
  }

  if (!passwordStrengthRegexSpecialChar.test(password)) {
    return 'Password must contain at least one special character.'
  }

  if (password !== second_password) {
    return 'Passwords do not match.'
  }

  return null
}
