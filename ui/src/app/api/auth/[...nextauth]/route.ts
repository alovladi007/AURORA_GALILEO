import NextAuth from "next-auth"
import CredentialsProvider from "next-auth/providers/credentials"
import { apiClient } from "@/lib/api-client"

const authOptions = {
  providers: [
    CredentialsProvider({
      name: "Credentials",
      credentials: {
        username: { label: "Username", type: "text" },
        password: { label: "Password", type: "password" }
      },
      async authorize(credentials: any) {
        try {
          const response = await apiClient.post('/auth/token', {
            username: credentials?.username,
            password: credentials?.password
          })

          if (response.data.access_token) {
            // Get user info
            const userResponse = await apiClient.get('/auth/me', {
              headers: {
                Authorization: `Bearer ${response.data.access_token}`
              }
            })

            return {
              id: userResponse.data.id,
              name: userResponse.data.username,
              email: userResponse.data.email,
              accessToken: response.data.access_token
            }
          }

          return null
        } catch (error) {
          console.error('Auth error:', error)
          return null
        }
      }
    })
  ],
  callbacks: {
    async jwt({ token, user }: any) {
      if (user) {
        token.accessToken = user.accessToken
        token.id = user.id
      }
      return token
    },
    async session({ session, token }: any) {
      session.accessToken = token.accessToken
      session.user.id = token.id
      return session
    }
  },
  pages: {
    signIn: '/auth/signin',
    error: '/auth/error',
  },
  secret: process.env.NEXTAUTH_SECRET || 'your-secret-key-change-in-production'
}

const handler = NextAuth(authOptions)

export { handler as GET, handler as POST }
