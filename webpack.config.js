const path = require('path');


module.exports = {
    mode: 'development',
    entry: './index.js',

    output: {
        filename: 'index.bundle.js',
        path: path.resolve(__dirname, '/var/www/aurora-borealis'),
    },

    module: {
        rules: [
            {
                test: /\.css$/,
                use: [
                    'style-loader',
                    'css-loader',
                ],
            },
            {
                test: /\.js$/,
                exclude: /node_modules/,
                use: {
                    loader: 'babel-loader',
                    options: {
                        presets: ['@babel/preset-env']
                    }
                }
            }
        ]
    }
};
