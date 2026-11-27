
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import App from './App'
import { ThemeProvider } from './context/ThemeContext'

describe('TaskFlow AI application', () => {
  it('renders the chat application and composer', () => {
    render(
      <ThemeProvider>
        <App />
      </ThemeProvider>,
    )

    expect(
      screen.getByRole('heading', {
        name: /Everything you need to stay on track/i,
      }),
    ).toBeInTheDocument()

    expect(
      screen.getByRole('textbox', { name: 'Message' }),
    ).toBeInTheDocument()

    expect(
      screen.getByRole('button', { name: 'New conversation' }),
    ).toBeInTheDocument()
  })
})
