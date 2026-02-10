export type AuthResponse = {
  token: string
}

export type AuthCredentials = {
  email: string
  password: string
}

export type RegisterCredentials = AuthCredentials & {
  name: string
}
