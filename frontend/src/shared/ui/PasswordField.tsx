import { forwardRef, useState } from 'react'
import { IconButton, InputAdornment, SvgIcon, TextField, type TextFieldProps } from '@mui/material'

type Props = Omit<TextFieldProps, 'type' | 'variant' | 'slotProps'>

export const PasswordField = forwardRef<HTMLDivElement, Props>(function PasswordField(props, ref) {
  const [visible, setVisible] = useState(false)
  const action = visible ? 'Скрыть пароль' : 'Показать пароль'
  return (
    <TextField
      {...props}
      ref={ref}
      type={visible ? 'text' : 'password'}
      variant="outlined"
      slotProps={{
        input: {
          endAdornment: (
            <InputAdornment position="end">
              <IconButton
                type="button"
                title={action}
                aria-label={action}
                aria-pressed={visible}
                edge="end"
                disabled={props.disabled}
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => setVisible((current) => !current)}
              >
                <SvgIcon aria-hidden="true">
                  <path
                    d="M2 12C4.5 8 8 6 12 6s7.5 2 10 6c-2.5 4-6 6-10 6S4.5 16 2 12Z"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.7"
                  />
                  <circle
                    cx="12"
                    cy="12"
                    r="2.5"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.7"
                  />
                  {visible && (
                    <path d="m4 4 16 16" fill="none" stroke="currentColor" strokeWidth="1.7" />
                  )}
                </SvgIcon>
              </IconButton>
            </InputAdornment>
          ),
        },
      }}
    />
  )
})
