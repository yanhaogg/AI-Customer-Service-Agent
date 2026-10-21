const BASE_URL =
"http://localhost:8000"



export async function request(
    url,
    options={}
){

    const token =
    localStorage.getItem(
        "token"
    )


    return fetch(
        BASE_URL + url,
        {

            ...options,

            headers:{
                "Content-Type":
                "application/json",

                Authorization:
                `Bearer ${token}`
            }

        }
    )

}