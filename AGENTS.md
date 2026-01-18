Important instructions:
* Never delete the `test-ecommerce-app` folder: the tests take care of cleaning its contents, so heavy-to-create files like `node_modules` are not deleted.
* It’s enough to run `test_ecommerce_backend` to verify that SQL generation works, and `test_ecommerce_frontend` for JavaScript generation. Both clean and regenerate everything before checking the SQL or the JS and leave it in `test-ecommerce-app`
* Never generate the code running `unibizkit` or `unibizkit.CLI`. Just run `test_ecommerce_backend` or `test_ecommerce_frontend`.
* Write commit messages in English and keep them concise and to the point.
* Test execution may take longer than 60 seconds. Do not set any time limits on running the tests.
