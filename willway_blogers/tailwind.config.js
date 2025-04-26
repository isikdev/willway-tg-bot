/** @type {import('tailwindcss').Config} */
module.exports = {
    content: [
        "./templates/**/*.html",
        "./static/**/*.js",
    ],
    theme: {
        extend: {
            colors: {
                primary: {
                    DEFAULT: '#154c47',
                    light: '#1f605b',
                    dark: '#0b3833',
                }
            },
            fontFamily: {
                sans: ['Inter var', 'system-ui', '-apple-system', 'sans-serif'],
            },
            spacing: {
                '18': '4.5rem',
                '22': '5.5rem',
            },
            borderRadius: {
                'xl': '1rem',
                '2xl': '1.5rem',
            },
            animation: {
                'fade-in': 'fadeIn 0.5s ease-in-out',
                'slide-up': 'slideUp 0.5s ease-in-out',
            },
        },
    },
    plugins: [
        require('@tailwindcss/forms'),
    ],
} 